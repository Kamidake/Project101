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

# The strict list of groups you want to keep
ALLOWED_GROUPS = {'NBA', 'Combat Sports', 'Boxing', 'AEW', 'WWE', 'UFC', 'TNA'}


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
    """Keep each website event; deduplicate and filter streams older than 1 hour."""
    unique = {}
    
    # Calculate timestamp for 1 hour ago (3600 seconds)
    cutoff_time = time.time() - 3600
    
    for source in entries:
        entry = dict(source)
        
        # Check if stream ended/started over an hour ago
        stream_time = entry.get('ends_at') or entry.get('starts_at') or 0
        if stream_time and stream_time < cutoff_time:
            continue
        
        # Check for 'tna' or 'ufc' across multiple potential keys
        page_val = str(entry.get('page', '')).lower()
        url_val = str(entry.get('url', '')).lower()
        referer_val = str(entry.get('referer', '')).lower()
        name_val = str(entry.get('name', '')).lower()
        
        search_string = f"{page_val} {url_val} {referer_val} {name_val}"
        
        # Using word boundaries to prevent false positives
        if re.search(r'\btna\b', search_string):
            entry['group'] = 'TNA'
        elif re.search(r'\bufc\b', search_string):
            entry['group'] = 'UFC'
        # Populate the group dynamically if it is missing
        elif 'group' not in entry and 'url' in entry:
            entry['group'] = roxie_group(entry['url'])
        
        # SKIP any stream that is not in our allowed list
        if entry.get('group') not in ALLOWED_GROUPS:
            continue
            
        entry['name'] = clean_title(entry['name'])
        
        # Capture the original URL for deduplication identity
        original_url = entry['url']
        identity = (entry['name'], original_url, entry.get('starts_at') or 0)
        
        if identity in unique:
            continue
            
        entry['poster'] = entry.get('poster') or fallback_logo(entry.get('group'))
        entry['event_id'] = f"{entry.get('group')}:{entry['name']}:{identity[2]}"
        entry['provider'] = entry.get('provider', 'RoxieStreams')
        
        # Generate a stable TVG ID based on the unique identity tuple
        entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(repr(identity).encode()).hexdigest()[:16]
        entry['display_name'] = entry['name']
            
        unique[identity] = entry
        
    # Sort the final output by Group -> Name -> URL
    return sorted(unique.values(), key=lambda e: (e.get('group', ''), e['name'], e['url']))
