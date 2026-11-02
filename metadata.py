import hashlib
import html
import time  # Required by test_schedule.py mocks
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


def roxie_group(page):
    """Determines the group based on the URL path slug."""
    slug = urlsplit(page).path.strip('/').split('-')[0].lower()
    return GROUPS.get(slug, 'Live')


def fallback_logo(group):
    """Returns the default logo URL for a given group."""
    return LOGO_BASE + LOGOS.get(group, 'live') + '.png'


def decorate(entries):
    """Remove duplicate URLs, keep alternates numbered, and use identical TVG IDs to merge EPG."""
    unique = {}
    event_counts = {}
    
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
            
        entry['name'] = clean_title(entry.get('name', ''))
        
        # Core event identity (Group + Name + Start Time)
        event_key = (entry.get('group'), entry['name'], entry.get('starts_at') or 0)
        
        # Unique stream identity (Core Event + Stream URL)
        original_url = entry.get('url', '')
        stream_identity = (event_key, original_url)
        
        # Drop exact duplicate URLs for the same event
        if stream_identity in unique:
            continue
            
        # Track alternates and number them
        if event_key not in event_counts:
            event_counts[event_key] = 1
        else:
            event_counts[event_key] += 1
            entry['name'] = f"{entry['name']} ({event_counts[event_key]})"
            
        entry['poster'] = entry.get('poster') or fallback_logo(entry.get('group'))
        entry['event_id'] = f"{entry.get('group')}:{entry['name']}:{event_key[2]}"
        entry['provider'] = entry.get('provider', 'RoxieStreams')
        
        # Generate the TVG ID using ONLY the event details (not the URL)
        # This ensures all alternate streams share the same EPG listing
        entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(repr(event_key).encode()).hexdigest()[:16]
        entry['display_name'] = entry['name']
            
        unique[stream_identity] = entry
        
    return sorted(unique.values(), key=lambda e: (e.get('group', ''), e.get('name', ''), e.get('url', '')))
