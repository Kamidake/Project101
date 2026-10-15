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
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from metadata import clean_title, decorate, roxie_group

BASE = os.getenv('SOURCE_URL', 'https://roxiestreams.info/').rstrip('/') + '/'
BACKUPS = tuple(x.rstrip('/')+'/' for x in os.getenv('ROXIE_BACKUP_URLS','https://roxiestreams.biz/,https://roxiestreams.su/').split(',') if x.strip())
ROXIE_HOSTS = {'roxiestreams.info','roxiestreams.biz','roxiestreams.su'}
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


class ScheduleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.td_index = 0
        
        self.events = []
        self.current_event = {}
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table' and ('eventsTable' in attrs.get('id', '') or 'schedule' in attrs.get('class', '')):
            self.in_table = True
        elif self.in_table and tag == 'tbody':
            self.in_tbody = True
        elif (self.in_table or self.in_tbody) and tag == 'tr':
            self.in_tr = True
            self.current_event = {}
            self.td_index = 0
        elif self.in_tr and tag == 'td':
            self.in_td = True
            self.current_text = []
        elif self.in_td and tag == 'a' and self.td_index == 0:
            self.current_event['url'] = attrs.get('href', '')

    def handle_data(self, data):
        if self.in_td:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == 'table' and self.in_table:
            self.in_table = False
        elif tag == 'tbody' and self.in_tbody:
            self.in_tbody = False
        elif tag == 'tr' and self.in_tr:
            self.in_tr = False
            if 'name' in self.current_event and self.current_event['name']:
                self.events.append(self.current_event)
        elif tag == 'td' and self.in_td:
            self.in_td = False
            text = ''.join(self.current_text).strip()
            
            if self.td_index == 0:
                self.current_event['name'] = text
            elif self.td_index == 1:
                self.current_event['start_time'] = text
                
            self.td_index += 1


def parse_schedules(html_text):
    parser = ScheduleParser()
    parser.feed(html_text)
    return parser.events


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


def internal_links(text, page, base=None):
    base = base or BASE
    parser = Links()
    parser.feed(text)
    for href, label in parser.links:
        url = urljoin(page, href).split('#')[0]
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https'):
            continue
        if parts.hostname in ROXIE_HOSTS:
            target = urlsplit(base)
            url = urlunsplit((target.scheme,target.netloc,parts.path,parts.query,''))
            parts = urlsplit(url)
        if parts.netloc != urlsplit(base).netloc:
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
        # REMOVED group-title entirely from the M3U EXTINF line
        lines += [f'#EXTINF:-1 tvg-id="{safe(entry.get("tvg_id", ""))}" tvg-name="{safe(entry["name"])}" tvg-logo="{safe(entry.get("poster", ""))}",{safe(entry.get("display_name", entry["name"]))}',
                  f'#EXTVLCOPT:http-referrer={entry["page"]}',
                  f'#EXTVLCOPT:http-user-agent={UA}', entry['url']]
    return '\n'.join(lines) + '\n'


def render_epg(entries):
    """Generate XMLTV EPG code for the playlist entries."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="Project101 EPG">']
    
    # 1. Define all channels
    for entry in entries:
        tvg_id = safe(entry.get("tvg_id", ""))
        name = html.escape(entry.get("display_name", entry["name"]))
        poster = html.escape(entry.get("poster", ""))
        
        lines.append(f'  <channel id="{tvg_id}">')
        lines.append(f'    <display-name>{name}</display-name>')
        if poster:
            lines.append(f'    <icon src="{poster}" />')
        lines.append('  </channel>')
        
    # 2. Add Programmes (Events) for channels that have times
    for entry in entries:
        if 'xmltv_start' in entry and 'xmltv_stop' in entry:
            tvg_id = safe(entry.get("tvg_id", ""))
            # Use base_name so the EPG title doesn't display the time (since the EPG grid already shows it)
            title = html.escape(entry.get("base_name", entry["name"]))
            
            lines.append(f'  <programme start="{entry["xmltv_start"]}" stop="{entry["xmltv_stop"]}" channel="{tvg_id}">')
            lines.append(f'    <title lang="en">{title}</title>')
            lines.append(f'    <desc lang="en">Live event: {title}</desc>')
            lines.append('  </programme>')
            
    lines.append('</tv>')
    return '\n'.join(lines) + '\n'


def write_playlist_if_changed(content, path):
    encoded = content.encode('utf-8')
    if path.is_file() and path.read_bytes() == encoded:
        return False
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return True


def discover_roxie(base, pool):
    pages, errors, labels = {}, [], {base:'RoxieStreams'}
    pending = {base}
    for _ in range(5):
        batch = sorted(pending - pages.keys())
        print(f'Crawl batch: {len(batch)} pages on {base}', flush=True)
        if not batch:
            break
        if len(pages) + len(batch) > 200:
            raise RuntimeError('Crawl exceeded 200 pages; review website structure')
        pending = set()
        futures = {pool.submit(fetch, url, base):url for url in batch}
        for future in concurrent.futures.as_completed(futures):
            page = futures[future]
            try:
                text = future.result()
                pages[page] = text
                for url, label in internal_links(text,page,base):
                    if label:
                        labels.setdefault(url,label)
                    if url not in pages:
                        pending.add(url)
            except Exception as exc:
                pages[page] = ''
                if 'HTTP Error 404' not in str(exc):
                    errors.append({'page': page, 'error': str(exc)})
                else:
                    print(f'Skipped dead link (404): {page}', flush=True)
    if pending - pages.keys():
        errors.append({'error':'Crawl depth limit reached'})
    return pages, labels, errors


def match_schedule_time(name, page_path, group, schedule_lookup_url, schedule_lookup_name, schedule_by_group):
    norm_name = clean_title(name).casefold()

    if page_path in schedule_lookup_url:
        return schedule_lookup_url[page_path]

    if norm_name in schedule_lookup_name:
        return schedule_lookup_name[norm_name]

    for sched_name, s_time in schedule_lookup_name.items():
        if sched_name in norm_name or norm_name in sched_name:
            return s_time

    keywords = {
        'AEW': ['aew', 'dynamite', 'rampage', 'collision', 'revolution', 'all out', 'double or nothing'],
        'NBA': ['nba', 'preseason'],
        'WWE': ['wwe', 'raw', 'smackdown', 'nxt'],
        'UFC': ['ufc', 'contender series', 'fight night'],
        'TNA': ['tna', 'impact'],
    }
    for cat, terms in keywords.items():
        if group == cat or any(t in norm_name for t in terms):
            if cat in schedule_by_group:
                return schedule_by_group[cat]

    return schedule_by_group.get(group)


def collect_roxie(pages, labels, schedule_list):
    errors = []
    candidates = {}
    unsupported = []
    event_labels = {}
    
    schedule_lookup_url = {}
    schedule_lookup_name = {}
    schedule_by_group = {}

    for event in schedule_list:
        start_time = event.get('start_time')
        if not start_time:
            continue
        if 'url' in event and event['url']:
            path = urlsplit(event['url']).path.strip('/')
            schedule_lookup_url[path] = start_time
            grp = roxie_group(event['url'])
            if grp and grp != 'Live':
                schedule_by_group.setdefault(grp, start_time)

        if 'name' in event and event['name']:
            norm = clean_title(event['name']).casefold()
            schedule_lookup_name[norm] = start_time
            
            if 'aew' in norm:
                schedule_by_group.setdefault('AEW', start_time)
            elif 'nba' in norm:
                schedule_by_group.setdefault('NBA', start_time)
            elif 'wwe' in norm or 'nxt' in norm:
                schedule_by_group.setdefault('WWE', start_time)
            elif 'ufc' in norm or 'contender' in norm:
                schedule_by_group.setdefault('UFC', start_time)

    for parent, text in sorted(pages.items()):
        if urlsplit(parent).path.strip('/'):
            for target, label in internal_links(text, parent):
                if label:
                    event_labels.setdefault(target, set()).add(clean_title(label))
                    
    for page, text in sorted(pages.items()):
        try:
            page_path = urlsplit(page).path.strip('/')
            sources = extract_sources(text, page)
            group = roxie_group(page)
            
            for url in sources:
                names_to_use = sorted(event_labels.get(page) or {clean_title(labels.get(page) or page_path)})
                for name in names_to_use:
                    candidate_dict = {
                        'name': name, 'group': group, 'provider': 'RoxieStreams',
                        'page': page, 'url': url
                    }
                    start_time = match_schedule_time(name, page_path, group, schedule_lookup_url, schedule_lookup_name, schedule_by_group)
                    if start_time:
                        candidate_dict['start_time'] = start_time
                    candidates.setdefault(url, []).append(candidate_dict)
                    
            if not sources and re.search(r'<(?:iframe|video)\b', text):
                unsupported.append(page)
        except Exception as exc:
            errors.append({'page': page, 'error': str(exc)})
            
    return candidates, unsupported, errors


def select_roxie(pool):
    global BASE
    attempts = []
    schedule = []
    for base in dict.fromkeys((BASE, *BACKUPS)):
        BASE = base
        try:
            pages, labels, errors = discover_roxie(base, pool)
            
            all_schedules = []
            seen_events = set()
            for page_url, html_content in pages.items():
                if html_content:
                    for ev in parse_schedules(html_content):
                        key = (ev.get('name'), ev.get('start_time'))
                        if key not in seen_events:
                            seen_events.add(key)
                            all_schedules.append(ev)
            schedule = all_schedules

            candidates, unsupported, source_errors = collect_roxie(pages, labels, schedule)
            errors.extend(source_errors)
            
            if not candidates:
                errors.append({'error':'No HLS sources discovered'})

        except Exception as exc:
            pages, candidates, unsupported, errors = {}, {}, [], [{'error':str(exc)}]
            
        attempts.append({'base':base,'pages':len(pages),'errors':errors.copy()})
        if not errors:
            break
        print(f'Incomplete discovery on {base}; trying backup',flush=True)
        
    return pages, candidates, unsupported, errors, attempts, schedule


def main():
    print('Discovering stream pages...', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        pages, candidates, unsupported, errors, attempts, schedule = select_roxie(pool)
        entries, unavailable = [], 0
        print(f'Checking {len(candidates)} HLS URLs from {len(pages)} pages...', flush=True)
        def check(aliases):
            for entry in aliases:
                try:
                    if live_media(entry['url'], entry['page']):
                        return [dict(alias, page=entry['page']) for alias in aliases]
                except Exception:
                    pass
            return None
            
        for index, result in enumerate(pool.map(check, candidates.values()), 1):
            if index % 10 == 0:
                print(f'Checked {index}/{len(candidates)} URLs', flush=True)
            if result:
                entries.extend(result)
            else:
                unavailable += 1
                
    entries = decorate(entries)
    
    report = {'updated_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'pages': len(pages),
              'candidate_urls': len(candidates), 'live_urls': len(entries), 'unavailable_urls': unavailable,
              'unsupported_pages': unsupported, 'errors': errors,
              'event_groups':len({e['event_id'] for e in entries}),
              'event_posters':sum('assets/logos/' not in e['poster'] for e in entries),
              'schedule': schedule, 
              'roxie_source':BASE,'roxie_attempts':attempts}
              
    Path('status.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    
    if errors or not candidates:
        raise RuntimeError('Incomplete discovery; playlist was not updated. See status.json.')
        
    # --- WRITE M3U AND EPG XML ---
    changed_m3u = write_playlist_if_changed(render(entries), Path('playlist.m3u'))
    changed_epg = write_playlist_if_changed(render_epg(entries), Path('epg.xml'))
    
    if changed_m3u or changed_epg:
        print('Playlist and EPG updated.', flush=True)
    else:
        print('Playlist and EPG unchanged; no update needed.', flush=True)


if __name__ == '__main__':
    main()
