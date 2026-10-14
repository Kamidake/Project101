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
            if event.get('name'):
                schedule[event['name'].casefold()] = unix_time
            if event.get('shortName'):
                schedule[event['shortName'].casefold()] = unix_time
                
            # Method B: Extract Competitors (Best for NBA)
            try:
                competitors = event['competitions'][0]['competitors']
                name1 = competitors[0].get('team', {}).get('name') or competitors[0].get('athlete', {}).get('displayName')
                name2 = competitors[1].get('team', {}).get('name') or competitors[1].get('athlete', {}).get('displayName')
                
                if name1 and name2:
                    name1, name2 = name1.casefold(), name2.casefold()
                    schedule[(name1, name2)] = unix_time
            except (KeyError, IndexError):
                pass
                
    except Exception as e:
        print(f"DEBUG: Failed to fetch {league.upper()} schedule from ESPN: {e}")
        
    return schedule


def decorate(entries):
    """Dedupe URLs; strictly include only specific groups; conditionally group events."""
    
    # NFL and NHL removed from allowed groups
    allowed_groups = {'nba', 'ufc', 'boxing', 'combat sports', 'wwe', 'live'}
    
    # 1. DOWNLOAD SCHEDULES ONLY FOR RELEVANT LEAGUES
    found_leagues = {str(e.get('group', '')).strip().casefold() for e in entries}
    schedules = {}
    # Check only for NBA and UFC
    for league in ['nba', 'ufc']:
        if league in found_leagues:
            schedules[league] = get_espn_schedule(league)
    
    by_url = defaultdict(list)
    for entry in entries:
        # INCLUSION LOGIC: Skip any stream whose group is not in the allowed list
        group = str(entry.get('group', '')).strip().casefold()
        if not group or group not in allowed_groups:
            continue
            
        # 2. MATCH THE SCRAPED NAME TO THE EXTERNAL ESPN SCHEDULE
        name_clean = entry['name'].casefold()
        league_schedule = schedules.get(group, {})
        
        for game_key, start_time in league_schedule.items():
            if isinstance(game_key, tuple):
                team1, team2 = game_key
                if team1 in name_clean and team2 in name_clean:
                    entry['starts_at'] = start_time
                    break
            elif isinstance(game_key, str):
                if game_key in name_clean or name_clean in game_key:
                    entry['starts_at'] = start_time
                    break
                    
        by_url[entry['url']].append(dict(entry))
        
    unique = []
    for url, aliases in sorted(by_url.items()):
        aliases.sort(key=lambda e: (e.get('provider', 'RoxieStreams'), e['page'], e['name']))
        entry = aliases[0]
        names = {event_key(e['name']) for e in aliases}
        entry['provider'] = ' + '.join(sorted({e.get('provider', 'RoxieStreams') for e in aliases}))
        
        if len(names) > 1:
            channel = urlsplit(url).path.rsplit('/', 1)[-1].removesuffix('.m3u8')
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
    
    # Removed NFL and NHL from groups_to_number
    groups_to_number = {'nba', 'ufc', 'boxing', 'combat sports', 'wwe', 'ppv', 'pay per view'}
    
    # Process all unique streams into groups for uniform date/time formatting
    for entry in unique:
        grouped_streams[entry['event_id']].append(entry)
            
    # Process and format all streams
    for key in sorted(grouped_streams):
        feeds = sorted(grouped_streams[key], key=lambda e: (e['provider'], e.get('source_tag', ''), e['url']))
        for index, entry in enumerate(feeds, 1):
            details = []
            
            # 3. ADD DATE & TIME HERE (Philippine Time)
            if entry.get('starts_at'):
                try:
                    # Force starts_at to be an integer
                    timestamp = int(entry['starts_at'])
                    # Add 8 hours (28800 seconds) to the UTC timestamp for PHT
                    pht_timestamp = timestamp + 28800
                    event_time = time.strftime('%b %d, %I:%M %p', time.gmtime(pht_timestamp))
                    
                    # Append time to the base name
                    entry['name'] = f"{entry['name']} [{event_time}]"
                except (ValueError, TypeError):
                    pass 

            # 4. Add Feed Number (if applicable)
            is_numbered_group = str(entry.get('group', '')).casefold() in groups_to_number
            if is_numbered_group and len(feeds) > 1:
                details.append(f'Feed {index}')
                
            # 5. Add Provider & Locale info
            details.extend(provider for provider in entry['provider'].split(' + ') if provider.casefold() != 'roxiestreams')
            if entry.get('source_tag'):
                details.append(entry['source_tag'])
            if entry.get('locale'):
                details.append(entry['locale'].upper())
                
            # 6. Build Final Display Name
            title = entry['name'] if entry['name'].casefold().startswith(entry['group'].casefold()) else f'{entry["group"]} | {entry["name"]}'
            entry['display_name'] = title + (' — ' + ' · '.join(details) if details else '')
            
            # 7. EXPLICITLY SET TVG-NAME
            entry['tvg_name'] = entry['name'] 
            
            result.append(entry)
            
    # Sort the final combined output by group and then event name
    return sorted(result, key=lambda e: (e.get('group', ''), e.get('name', '')))
