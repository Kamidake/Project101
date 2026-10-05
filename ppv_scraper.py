"""Independent exporter for publicly supplied PPV HLS URLs."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import time
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, urlopen

BASES = ['https://api.ppv.st/api', 'https://api.ppv.cx/api']
UA = 'Mozilla/5.0 (compatible; ZeroStreamsPPV/1.0)'


def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':UA,'Referer':'https://ppv.st/'}),timeout=15) as response:
        return response.read(2_000_000).decode('utf-8-sig')


def api(url):
    data=json.loads(fetch(url))
    if data.get('success') is not True:
        raise ValueError('Unsuccessful API response')
    return data


def catalog():
    bases=list(BASES)
    for base in BASES:
        try:
            for domain in api(base+'/ping').get('domains',[]):
                if not isinstance(domain,str): continue
                host=urlsplit(domain if '://' in domain else 'https://'+domain).hostname
                if host and host.startswith(('ppv.','ppvs.','api.ppv.')):
                    candidate='https://'+(host if host.startswith('api.') else 'api.'+host)+'/api'
                    if candidate not in bases: bases.append(candidate)
            break
        except Exception: continue
    errors=[]
    for base in bases:
        try:
            data=api(base+'/streams')
            if not isinstance(data.get('streams'),list): raise ValueError('Missing categories')
            return base,data['streams']
        except Exception as exc: errors.append(str(exc))
    raise RuntimeError('All API mirrors failed: '+str(errors))


def active(item,category,now):
    if item.get('always_live') in (1,True,'1') or category.get('always_live') in (1,True,'1'): return True
    start,end=int(item.get('starts_at') or 0),int(item.get('ends_at') or 0)
    return start>0 and start<=now and (not end or now<end)


def direct_sources(item):
    if item.get('auth') or item.get('vip_stream'): return []
    values=[item.get('m3u8'),item.get('playlist_full')]
    values += [s.get('data') for s in item.get('sources',[]) if s.get('type') in ('hls','m3u8','playlist')]
    return sorted({v for v in values if isinstance(v,str) and urlsplit(v).scheme in ('http','https') and urlsplit(v).path.lower().endswith('.m3u8')})


def live(url,depth=0):
    if depth>3: return False
    text=fetch(url)
    if not text.lstrip().startswith('#EXTM3U') or '#EXT-X-ENDLIST' in text: return False
    lines=[x.strip() for x in text.splitlines() if x.strip() and not x.startswith('#')]
    if '#EXT-X-STREAM-INF:' in text:
        for variant in lines[:3]:
            try:
                if live(urljoin(url,variant),depth+1): return True
            except Exception: continue
        return False
    if '#EXTINF:' not in text or not lines: return False
    with urlopen(Request(urljoin(url,lines[-1]),headers={'User-Agent':UA,'Referer':'https://ppv.st/','Range':'bytes=0-1023'}),timeout=15) as response:
        return bool(response.read(1024))


def clean(value):
    return ' '.join(html.unescape(str(value or '')).replace('"',"'").split())


def render(entries):
    lines=['#EXTM3U']; groups={}; seen=set()
    for e in sorted(entries,key=lambda e:(e['group'],e['name'],e['url'])):
        if e['url'] in seen: continue
        seen.add(e['url']); groups.setdefault((e['group'],e['name']),[]).append(e)
    for key,feeds in sorted(groups.items()):
        for n,e in enumerate(feeds,1):
            title=clean(e['group'])+' | '+clean(e['name'])
            tags=([f'Feed {n}'] if len(feeds)>1 else [])+[clean(e.get('tag'))]
            tags=[tag for tag in tags if tag]
            if tags: title+=' — '+' · '.join(tags)
            identity='ppv.'+hashlib.sha256((str(e.get('id'))+urlsplit(e['url']).netloc+urlsplit(e['url']).path).encode()).hexdigest()[:16]
            lines += [f'#EXTINF:-1 tvg-id="{identity}" tvg-name="{clean(e["name"])}" tvg-logo="{clean(e.get("poster"))}" group-title="{clean(e["group"])}",{title}', '#EXTVLCOPT:http-referrer=https://ppv.st/', '#EXTVLCOPT:http-user-agent='+UA, e['url']]
    return '\n'.join(lines)+'\n'


def write_if_changed(path,content):
    data=content.encode()
    if path.exists() and path.read_bytes()==data: return False
    temp=path.with_suffix(path.suffix+'.tmp'); temp.write_bytes(data); temp.replace(path)
    return True


def main():
    report={'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        base,categories=catalog(); entries=[]; events=[]; embed_only=0; unavailable=0
        for category in categories:
            for item in category.get('streams',[]):
                if not active(item,category,int(time.time())): continue
                events.append({'name':item.get('name'),'page':'https://ppv.st/live/'+str(item.get('uri_name') or ''),'poster':item.get('poster')})
                found=False
                for variant in [item]+list(item.get('substreams') or []):
                    if item.get('auth') or item.get('vip_stream'): continue
                    for url in direct_sources(variant):
                        found=True
                        try: reachable=live(url)
                        except Exception: reachable=False
                        if not reachable: unavailable+=1; continue
                        entries.append({'id':variant.get('id',item.get('id')),'name':item.get('name') or 'Live Stream','group':category.get('category') or 'Live','poster':item.get('poster') or '', 'tag':variant.get('source_tag') or item.get('tag') or '', 'url':url})
                if not found: embed_only+=1
        report.update(api=base,active_events=len(events),embed_only_events=embed_only,live_urls=len({e['url'] for e in entries}),unavailable_urls=unavailable,events=events,status='direct-hls' if entries else 'no-playable-direct-hls')
        report['playlist_changed']=write_if_changed(Path('ppv.m3u'),render(entries))
    except Exception as exc:
        report.update(status='failed',error=str(exc)); raise
    finally:
        Path('ppv-status.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))

if __name__=='__main__': main()
