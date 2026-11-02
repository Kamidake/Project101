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


def roxie_group(page):
    """Determines the group based on the URL path slug."""
    slug = urlsplit(page).path.strip('/').split('-')[0].lower()
    return GROUPS.get(slug, 'Live')


def fallback_logo(group):
    """Returns the default logo URL for a given group."""
    return LOGO_BASE + LOGOS.get(group, 'live') + '.png'


def decorate(entries):
    """Keep each website event; deduplicate exact URLs and number alternates deterministically."""
    events = {}
    
    # Pass 1: Group all unique URLs by their core event
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
        
        # display_name remains un-numbered so the EPG groups them together cleanly
        entry['display_name'] = clean_name 
        
        # Core event identity (Group + Base Name + Start Time)
        event_key = (entry.get('group'), clean_name, entry.get('starts_at') or 0)
        url = entry.get('url', '')
        
        if event_key not in events:
            events[event_key] = {}
            
        # Only store the first instance of an exact URL for a given event
        if url not in events[event_key]:
            entry['poster'] = entry.get('poster') or fallback_logo(entry.get('group'))
            entry['event_id'] = f"{entry.get('group')}:{clean_name}:{event_key[2]}"
            entry['provider'] = entry.get('provider', 'RoxieStreams')
            events[event_key][url] = entry
            
    final_entries = []
    
    # Pass 2: Sort URLs to ensure alternate numbering is invariant to input order
    for event_key, url_dict in events.items():
        sorted_urls = sorted(url_dict.keys())
        
        for index, url in enumerate(sorted_urls):
            entry = url_dict[url]
            base_name = event_key[1]
            
            # Number alternate streams so they get unique channel listings
            if index == 0:
                entry['name'] = base_name
            else:
                entry['name'] = f"{base_name} ({index + 1})"
                
            # Generate the TVG ID using the numbered name so it is unique per alternate
            tvg_identity = (event_key[0], entry['name'], event_key[2])
            entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(repr(tvg_identity).encode()).hexdigest()[:16]
            
            final_entries.append(entry)
            
    return sorted(final_entries, key=lambda e: (e.get('group', ''), e.get('name', ''), e.get('url', '')))
