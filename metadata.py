from collections import defaultdict
import hashlib
import html
import re
import time
import unicodedata
from urllib.parse import urlsplit

LOGO_BASE = 'https://raw.githubusercontent.com/Kamidake/Project101/main/assets/logos/'
GROUPS = {'nfl':'NFL', 'redzone':'NFL', 'nba':'NBA', 'wnba':'WNBA', 'nhl':'NHL',
          'mlb':'MLB', 'soccer':'Soccer', 'f1':'Formula 1', 'nascar':'NASCAR',
          'motogp':'MotoGP', 'mxgp':'MXGP', 'wwe':'WWE', 'aew':'Combat Sports',
          'tna':'Combat Sports', 'ufc':'UFC', 'boxing':'Boxing', 
          'fighting':'Combat Sports', 'motorsports':'Motorsports'}
LOGOS = {'NFL':'nfl', 'NBA':'nba', 'WNBA':'wnba', 'NHL':'nhl', 'MLB':'mlb',
         'Soccer':'soccer', 'Formula 1':'formula-1', 'NASCAR':'nascar', 'MotoGP':'motogp',
         'MXGP':'mxgp', 'WWE':'wwe', 'UFC':'ufc', 'Boxing':'boxing',
         'Combat Sports':'combat-sports', 'Motorsports':'motorsports',
         'PPV':'boxing', 'Pay Per View':'boxing'} # Fallback logos for PPV if needed


def clean_title(value):
    value = ' '.join(html.unescape(str(value)).split())
    value = re.sub(r'\bvs\.?\s*', 'vs ', value, flags=re.I)
    value = re.sub(r'\s+at\s+', ' vs ', value, flags=re.I)
    value = re.sub(r'\bLA Clippers\b', 'Los Angeles Clippers', value)
    value = re.sub(r'\bDenamrk\b', 'Denmark', value)
    value = re.sub(r'\s*-\s*(Race|Malaysian Grand Prix)\b', r': \1', value)
    return value.strip()


def event_key(name):
    text = unicodedata.normalize('NFKD', clean_title(name)).casefold()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def roxie_group(page):
    slug = urlsplit(page).path.strip('/').split('-')[0].lower()
    return GROUPS.get(slug, 'Live')


def fallback_logo(group):
    return LOGO_BASE + LOGOS.get(group, 'live') + '.png'


def decorate(entries):
    """Dedupe URLs; strictly include only specific groups; conditionally group events."""
    
    # Define the strict whitelist of allowed groups (case-insensitive mapping)
    allowed_groups = {'nba', 'live', 'ufc', 'boxing', 'combat sports', 'wwe'}
    
    by_url = defaultdict(list)
    for entry in entries:
        # INCLUSION LOGIC: Skip any stream whose group is not in the allowed list
        group = str(entry.get('group', '')).strip().casefold()
        if not group or group not in allowed_groups:
            continue
            
        by_url[entry['url']].append(dict(entry))
        
    unique = []
    for url, aliases in sorted(by_url.items()):
        aliases.sort(key=lambda e: (e.get('provider','RoxieStreams'), e['page'], e['name']))
        entry = aliases[0]
        names = {event_key(e['name']) for e in aliases}
        entry['provider'] = ' + '.join(sorted({e.get('provider','RoxieStreams') for e in aliases}))
        
        if len(names) > 1:
            channel = urlsplit(url).path.rsplit('/',1)[-1].removesuffix('.m3u8')
            entry['name'] = channel.upper() + ' — Shared Feed'
            categories = {alias['group'] for alias in aliases}
            entry['group'] = next(iter(categories)) if len(categories) == 1 else 'Shared Channels'
            entry['poster'] = ''
        else:
            entry['name'] = clean_title(entry['name'])
            
        entry['poster'] = entry.get('poster') or fallback_logo(entry['group'])
        
        # Date avoids grouping repeat fixtures on different days.
        date = time.strftime('%Y-%m-%d', time.gmtime(entry.get('starts_at') or 0)) if entry.get('starts_at') else ''
        entry['event_id'] = f'{entry["group"]}:{event_key(entry["name"])}:{date}'
        identity = entry.get('identity') or f'{entry["provider"]}:{urlsplit(url).netloc}:{urlsplit(url).path}'
        entry['tvg_id'] = 'Lennon.' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        
        unique.append(entry)

    # Separate grouped streams from flat streams
    grouped_streams = defaultdict(list)
    result = []
    
    # Define which groups get the numbered feed logic
    groups_to_number = {'nba', 'ufc', 'boxing', 'combat sports', 'wwe', 'ppv', 'pay per view'}
    
    # Process all unique streams into groups for uniform date/time formatting
    for entry in unique:
        grouped_streams[entry['event_id']].append(entry)
            
    # Process and format all streams
    for key in sorted(grouped_streams):
        feeds = sorted(grouped_streams[key], key=lambda e:(e['provider'], e.get('source_tag',''), e['url']))
        for index, entry in enumerate(feeds, 1):
            details = []
            
            # 1. ADD DATE & TIME HERE (Philippine Time / PHT)
            if entry.get('starts_at'):
                # Add 8 hours (28800 seconds) to the UTC timestamp for UTC+8
                pht_timestamp = entry['starts_at'] + 28800
                event_time = time.strftime('%b %d, %I:%M %p PHT', time.gmtime(pht_timestamp))
                details.append(event_time)

            # 2. Add Feed Number (if applicable)
            is_numbered_group = str(entry.get('group', '')).casefold() in groups_to_number
            if is_numbered_group and len(feeds) > 1:
                details.append(f'Feed {index}')
                
            # 3. Add Provider & Locale info
            details.extend(provider for provider in entry['provider'].split(' + ') if provider.casefold() != 'roxiestreams')
            if entry.get('source_tag'):
                details.append(entry['source_tag'])
            if entry.get('locale'):
                details.append(entry['locale'].upper())
                
            # 4. Build Final Display Name
            title = entry['name'] if entry['name'].casefold().startswith(entry['group'].casefold()) else f'{entry["group"]} | {entry["name"]}'
            entry['display_name'] = title + (' — ' + ' · '.join(details) if details else '')
            result.append(entry)
            
    # Sort the final combined output by group and then event name
    return sorted(result, key=lambda e: (e.get('group', ''), e.get('name', '')))
