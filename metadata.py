import hashlib
import html
import time
import re
from urllib.parse import urlsplit

LOGO_BASE = 'https://raw.githubusercontent.com/Kamidake/Project101/main/assets/logos/'

GROUPS = {
    'nfl': 'NFL', 'redzone': 'NFL', 'nba': 'NBA', 'wnba': 'WNBA', 'nhl': 'NHL',
    'mlb': 'MLB', 'soccer': 'Soccer', 'f1': 'Formula 1', 'nascar': 'NASCAR',
    'motogp': 'MotoGP', 'mxgp': 'MXGP', 'wwe': 'WWE', 'ufc': 'UFC',
    'boxing': 'Boxing', 'fighting': 'Combat Sports', 'motorsports': 'Motorsports',
    'aew': 'AEW', 'tna': 'TNA'
}

LOGOS = {
    'NFL': 'nfl', 'NBA': 'nba', 'WNBA': 'wnba', 'NHL': 'nhl', 'MLB': 'mlb',
    'Soccer': 'soccer', 'Formula 1': 'formula-1', 'NASCAR': 'nascar', 'MotoGP': 'motogp',
    'MXGP': 'mxgp', 'WWE': 'wwe', 'UFC': 'ufc', 'Boxing': 'boxing',
    'Combat Sports': 'combat-sports', 'Motorsports': 'motorsports',
    'AEW': 'aew', 'TNA': 'tna'
}

ALLOWED_GROUPS = {'NBA', 'Combat Sports', 'Boxing', 'AEW', 'WWE', 'UFC', 'TNA'}

TNA_REGEX = re.compile(r'\btna\b')
UFC_REGEX = re.compile(r'\bufc\b')


def clean_title(value):
    """Cleans up HTML entities and extra whitespace."""
    return ' '.join(html.unescape(str(value)).split())


def normalize_for_identity(title):
    """Aggressively normalizes titles to group identical events with slight wording differences."""
    t = title.lower()
    for sep in [' vs. ', ' v ', ' @ ', ' at ', ' - ']:
        t = t.replace(sep, ' vs ')
    t = re.sub(r'[^a-z0-9 ]', '', t)
    return ' '.join(t.split())


def roxie_group(page):
    """Determines the group based on the URL path slug."""
    slug = urlsplit(page).path.strip('/').split('-')[0].lower()
    return GROUPS.get(slug, 'Live')


def fallback_logo(group):
    """Returns the default logo URL for a given group."""
    return LOGO_BASE + LOGOS.get(group, 'live') + '.png'


def decorate(entries):
    """Aggressively deduplicate events and streams to prevent EPG bloat."""
    events = {}
    
    for source in entries:
        entry = dict(source)
        
        page_val = str(entry.get('page', '')).lower()
        url_val = str(entry.get('url', '')).lower()
        referer_val = str(entry.get('referer', '')).lower()
        name_val = str(entry.get('name', '')).lower()
        
        search_string = f"{page_val} {url_val} {referer_val} {name_val}"
        
        if TNA_REGEX.search(search_string):
            entry['group'] = 'TNA'
        elif UFC_REGEX.search(search_string):
            entry['group'] = 'UFC'
        elif 'group' not in entry and 'url' in entry:
            entry['group'] = roxie_group(entry['url'])
        
        if entry.get('group') not in ALLOWED_GROUPS:
            continue
            
        clean_name = clean_title(entry.get('name', ''))
        identity_name = normalize_for_identity(clean_name)
        
        entry['display_name'] = clean_name 
        
        # Group events occurring within the same 1-hour block to catch slight schedule variations
        try:
            starts_at = int(entry.get('starts_at') or 0)
            starts_at_rounded = (starts_at // 3600) * 3600 if starts_at else 0
        except (ValueError, TypeError):
            starts_at_rounded = entry.get('starts_at')
        
        # Core event identity uses the fuzzed data to group effectively
        event_key = (entry.get('group'), identity_name, starts_at_rounded)
        
        # Strip query parameters/tokens for stream deduplication to drop useless exact-duplicates
        raw_url = entry.get('url', '').strip()
        parsed = urlsplit(raw_url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        if event_key not in events:
            events[event_key] = {}
            
        # Only add the stream if this base URL hasn't been added to this event yet
        if clean_url not in events[event_key]:
            entry['poster'] = entry.get('poster') or fallback_logo(entry.get('group'))
            entry['event_id'] = f"{entry.get('group')}:{clean_name}:{entry.get('starts_at') or 0}"
            entry['provider'] = entry.get('provider', 'RoxieStreams')
            events[event_key][clean_url] = entry
            
    final_entries = []
    
    # Pass 2: Sort URLs to ensure alternate numbering is deterministic
    for event_key, url_dict in events.items():
        sorted_urls = sorted(url_dict.keys())
        
        for index, clean_url in enumerate(sorted_urls):
            entry = url_dict[clean_url]
            base_name = entry['display_name']
            
            if index == 0:
                entry['name'] = base_name
            else:
                entry['name'] = f"{base_name} ({index + 1})"
                
            # TVG ID generated securely per alternate stream to satisfy EPG mapper/test
            tvg_identity = (event_key[0], entry['name'], event_key[2])
            entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(repr(tvg_identity).encode()).hexdigest()[:16]
            
            final_entries.append(entry)
            
    return sorted(final_entries, key=lambda e: (e.get('group', ''), e.get('name', ''), e.get('url', '')))
