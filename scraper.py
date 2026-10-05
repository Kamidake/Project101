"""Discover RoxieStreams HLS sources and export currently reachable live feeds."""
import concurrent.futures
import datetime as dt
import html
from functools import lru_cache
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

BASE = os.getenv('SOURCE_URL', 'https://roxiestreams.info/').rstrip('/') + '/'
UA = 'Mozilla/5.0 (compatible; LivePlaylist/1.0)'
TIMEOUT = 12


def fetch(url, referer=BASE):
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA, 'Referer': referer}), timeout=TIMEOUT) as response:
                return response.read(2_000_000).decode('utf-8', errors='replace')
        except Exception:
            if attempt:
                raise
            time.sleep(0.5)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None
        self.heading = False
        self.title = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.current = [attrs['href'], '']
        if tag in ('h1', 'h2') and not self.title:
            self.heading = True

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data
        if self.heading:
            self.title += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(tuple(self.current))
            self.current = None
        if tag in ('h1', 'h2'):
            self.heading = False


def internal_links(text, page):
    parser = Links()
    parser.feed(text)
    for href, label in parser.links:
        url = urljoin(page, href).split('#')[0]
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or parts.netloc != urlsplit(BASE).netloc:
            continue
        if parts.query or re.search(r'\.[a-zA-Z0-9]{2,5}$', parts.path) or parts.path == '/multiview':
            continue
        yield url, ' '.join(label.split())


@lru_cache(maxsize=64)
def load_domains(url, referer):
    return fetch(url, BASE)


def extract_sources(text, page, domain_loader=load_domains):
    text = html.unescape(text).replace(r'\/', '/')
    sources = set(re.findall(r'https?://[^\s\'"<>`]+\.m3u8(?:\?[^\s\'"<>`]*)?', text))
    calls = re.findall(r"getRandomStream\(\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]\s*(?:,\s*['\"]([^'\"]+)['\"])?\s*\)", text)
    if not calls:
        return sorted(sources)
    default = re.search(r"function\s+getRandomStream\([^)]*subdomain\s*=\s*['\"]([^'\"]+)", text)
    domains = []
    for name in set(re.findall(r"fetch\(\s*['\"]([^'\"]+\.txt)['\"]", text)):
        domains += [d.strip() for d in domain_loader(urljoin(page, name), BASE).splitlines() if re.fullmatch(r'[A-Za-z0-9.-]+', d.strip())]
    if not domains:
        raise ValueError('No current stream domains could be loaded')
    for path, subdomain in calls:
        for domain in sorted(set(domains)):
            sources.add(f'https://{subdomain or (default.group(1) if default else "admin2")}.{domain}/{path.lstrip("/")}')
    return sorted(sources)


def live_media(url, referer, depth=0):
    """Require a live media manifest and a reachable segment, not just HTTP 200."""
    if depth > 3:
        return False
    text = fetch(url, referer)
    if not text.lstrip('\ufeff').startswith('#EXTM3U') or '#EXT-X-ENDLIST' in text:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any(line.startswith('#EXT-X-STREAM-INF:') for line in lines):
        variants = [line for line in lines if not line.startswith('#')]
        return any(live_media(urljoin(url, variant), referer, depth + 1) for variant in variants[:3])
    segments = [line for line in lines if not line.startswith('#')]
    if not segments or '#EXTINF:' not in text:
        return False
    segment = urljoin(url, segments[-1])
    with urlopen(Request(segment, headers={'User-Agent': UA, 'Referer': referer, 'Range': 'bytes=0-1023'}), timeout=TIMEOUT) as response:
        return bool(response.read(1024))


def safe(value):
    return ' '.join(value.replace('"', "'").split())


def render(entries):
    lines = ['#EXTM3U']
    for entry in entries:
        lines += [f'#EXTINF:-1 group-title="{safe(entry["group"])}",{safe(entry["name"])}',
                  f'#EXTVLCOPT:http-referrer={entry["page"]}',
                  f'#EXTVLCOPT:http-user-agent={UA}', entry['url']]
    return '\n'.join(lines) + '\n'


def main():
    pages, errors, labels = {}, [], {BASE: 'RoxieStreams'}
    print('Discovering stream pages...', flush=True)
    pending = {BASE}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for _ in range(5):
            batch = sorted(pending - pages.keys())
            print(f'Crawl batch: {len(batch)} pages', flush=True)
            if not batch:
                break
            if len(pages) + len(batch) > 200:
                raise RuntimeError('Crawl exceeded 200 pages; review website structure')
            pending = set()
            futures = {pool.submit(fetch, url): url for url in batch}
            for future in concurrent.futures.as_completed(futures):
                page = futures[future]
                try:
                    text = future.result()
                    pages[page] = text
                    for url, label in internal_links(text, page):
                        if label:
                            labels.setdefault(url, label)
                        if url not in pages:
                            pending.add(url)
                except Exception as exc:
                    pages[page] = ''
                    errors.append({'page': page, 'error': str(exc)})
        if pending - pages.keys():
            errors.append({'error': 'Crawl depth limit reached'})
        candidates = {}
        unsupported = []
        for page, text in sorted(pages.items()):
            try:
                sources = extract_sources(text, page)
                for url in sources:
                    candidates.setdefault(url, {'name': labels.get(page) or urlsplit(page).path.strip('/'),
                                                'group': urlsplit(page).path.strip('/').split('-')[0].upper() or 'LIVE',
                                                'page': page, 'url': url})
                if not sources and re.search(r'<(?:iframe|video)\b', text):
                    unsupported.append(page)
            except Exception as exc:
                errors.append({'page': page, 'error': str(exc)})
        entries, unavailable = [], 0
        print(f'Checking {len(candidates)} HLS URLs from {len(pages)} pages...', flush=True)
        def check(entry):
            try:
                return entry if live_media(entry['url'], entry['page']) else None
            except Exception:
                return None
        for index, result in enumerate(pool.map(check, candidates.values()), 1):
            if index % 10 == 0:
                print(f'Checked {index}/{len(candidates)} URLs', flush=True)
            if result:
                entries.append(result)
            else:
                unavailable += 1
    entries.sort(key=lambda e: (e['group'], e['name'], e['url']))
    report = {'updated_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'pages': len(pages),
              'candidate_urls': len(candidates), 'live_urls': len(entries), 'unavailable_urls': unavailable,
              'unsupported_pages': unsupported, 'errors': errors}
    Path('status.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    # Fail closed: never publish an old playlist after an incomplete scan.
    if errors or not candidates:
        raise RuntimeError('Incomplete discovery; playlist was not updated. See status.json.')
    temporary = Path('playlist.m3u.tmp')
    temporary.write_text(render(entries), encoding='utf-8')
    temporary.replace('playlist.m3u')


if __name__ == '__main__':
    main()
