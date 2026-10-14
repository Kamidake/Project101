from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import time
import unicodedata
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

LOGO_BASE = 'https://raw.githubusercontent.com/Kamidake/Project101/main/assets/logos/'

GROUPS = {
    'nfl': 'NFL', 'redzone': 'NFL', 'nba': 'NBA', 'wnba': 'WNBA', 'nhl': 'NHL',
    'mlb': 'MLB', 'soccer': 'Soccer', 'f1': 'Formula 1', 'nascar': 'NASCAR',
    'motogp': 'MotoGP', 'mxgp': 'MXGP', 'wwe': 'WWE', 'aew': 'Combat Sports',
    'tna': 'Combat Sports', 'ufc': 'UFC', 'boxing': 'Boxing', 
    'fighting': 'Combat Sports', 'motorsports': 'Motorsports'
}

LOGOS = {
    'NFL': 'nfl', 'NBA': 'nba', 'WNBA': 'wnba', 'NHL': 'nhl', 'MLB': 'mlb',
    'Soccer': 'soccer', 'Formula 1': 'formula-1', 'NASCAR': 'nascar', 'MotoGP': 'motogp',
    'MXGP': 'mxgp', 'WWE': 'wwe', 'UFC': 'ufc', 'Boxing': 'boxing',
    'Combat Sports': 'combat-sports', 'Motorsports': 'motorsports',
    'PPV': 'boxing', 'Pay Per View': 'boxing' # Fallback logos for PPV if needed
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


def get_espn_schedule(league):
    """Fetches today's schedule from ESPN for NBA or UFC."""
    endpoints = {
        'nba': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
        'ufc': 'https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard'
    }
    
    schedule = {}
    url = endpoints.get(league)
    if not url:
        return schedule
        
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        for event in data.get('events', []):
            date_str = event.get('date')
            if not date_str:
                continue
                
            # Convert ISO string to a Unix timestamp
            dt_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            unix_time = int(dt_obj.timestamp())
            
            # Method A: Save the raw event name (Best for UFC, e.g., "UFC 300: Pereira vs. Hill")
            name = event.get('name')
            if name:
                schedule[event_key(name)] = unix_time
                
            # Method B: Save the short name (Good for NBA, e.g., "MIA @ BOS")
            short_name = event.get('shortName')
            if short_name:
                schedule[event_key(short_name)] = unix_time
                
    except Exception as e:
        print(f"Error fetching ESPN schedule for {league}: {e}")
        
    return schedule


def decorate(entries):
    """
    Removes duplicate URLs for the same event and numbers alternate streams.
    A repeated URL for different events is allowed (not mislabeled).
    """
    seen = set()
    result = []
    counts = {}

    for entry in entries:
        # Determine if the dictionary uses 'name' or 'title'
        name_key = 'name' if 'name' in entry else 'title'
        name = entry.get(name_key, '')
        url = entry.get('url', '')

        # Use combination of name and url to filter duplicates
        identifier = (name, url)
        if identifier in seen:
            continue
        seen.add(identifier)

        # Count occurrences of this specific event name for numbering alternates
        counts[name] = counts.get(name, 0) + 1
        count = counts[name]

        # Create a copy so we don't mutate the original dictionary
        new_entry = dict(entry)
        if count > 1:
            # Appends ' 2', ' 3', etc., to alternate streams.
            new_entry[name_key] = f"{name} {count}"
            
        result.append(new_entry)

    return result
