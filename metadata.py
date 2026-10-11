"""Consistent IPTV titles, category artwork, and feed labels, filtered for specific sports and excluding NCAA, NHL, & MLB."""
from collections import defaultdict
import hashlib
import html
import re
import time
import unicodedata
from urllib.parse import urlsplit

LOGO_BASE = 'https://raw.githubusercontent.com/Kamidake/Project101/main/assets/logos/'

# Updated GROUPS to map only the requested categories
GROUPS = {
    'nba': 'NBA', 
    'wwe': 'WWE', 
    'ufc': 'UFC',
    'boxing': 'Boxing', 
    'fighting': 'Combat Sports',
    'live': 'Live'
}

# Updated LOGOS to match the new GROUPS
LOGOS = {
    'NBA': 'nba', 
    'WWE': 'wwe', 
    'UFC': 'ufc', 
    'Boxing': 'boxing',
    'Combat Sports': 'combat-sports',
    'Live': 'live'
}


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


def is_excluded(entry):
    """Check if the entry relates to NCAA, NHL, or MLB by looking at the name and group."""
    name = str(entry.get('name', '')).casefold()
    group = str(entry.get('group', '')).casefold()
    
    # Exclude any stream if its name or group contains these terms
    excluded_terms = ['ncaa', 'nhl', 'mlb']
    return any(term in name or term in group for term in excluded_terms)


def decorate(entries):
    """Dedupe exact URLs; filter by allowed groups and exclude specific sports; merge matching event names, number distinct feeds."""
    
    # 1. Filter entries to only include allowed groups AND drop excluded terms
    allowed_groups = set(GROUPS.values())
    filtered_entries = [
        entry for entry in entries 
        if entry.get('group') in allowed_groups and not is_excluded(entry)
    ]

    by_url = defaultdict(list)
    for entry in filtered_entries:
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
        entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        unique.append(entry)
        
    groups = defaultdict(list)
    for entry in unique:
        groups[entry['event_id']].append(entry)
        
    result = []
    for key in sorted(groups):
        feeds = sorted(groups[key], key=lambda e:(e['provider'],e.get('source_tag',''),e['url']))
        for index, entry in enumerate(feeds,1):
            details = [f'Feed {index}'] if len(feeds)>1 else []
            details.extend(provider for provider in entry['provider'].split(' + ') if provider.casefold() != 'roxiestreams')
            
            if entry.get('source_tag'):
                details.append(entry['source_tag'])
            if entry.get('locale'):
                details.append(entry['locale'].upper())
                
            title = entry['name'] if entry['name'].casefold().startswith(entry['group'].casefold()) else f'{entry["group"]} | {entry["name"]}'
            entry['display_name'] = title + (' — ' + ' · '.join(details) if details else '')
            result.append(entry)
            
    return result
