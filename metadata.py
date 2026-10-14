"""Consistent IPTV titles, category artwork, and feed labels."""
import hashlib
import html
import re
import time
import unicodedata
from urllib.parse import urlsplit

LOGO_BASE = 'https://raw.githubusercontent.com/Kamidake/Project101/main/assets/logos/'

# Full mapping so unwanted sports get correctly identified (and then filtered out)
GROUPS = {'nfl':'NFL', 'redzone':'NFL', 'nba':'NBA', 'wnba':'WNBA', 'nhl':'NHL',
          'mlb':'MLB', 'soccer':'Soccer', 'f1':'Formula 1', 'nascar':'NASCAR',
          'motogp':'MotoGP', 'mxgp':'MXGP', 'wwe':'WWE', 'aew':'AEW', 'tna':'TNA', 'ufc':'UFC',
          'boxing':'Boxing', 'fighting':'Combat Sports', 'motorsports':'Motorsports'}

LOGOS = {'NFL':'nfl', 'NBA':'nba', 'WNBA':'wnba', 'NHL':'nhl', 'MLB':'mlb',
         'Soccer':'soccer', 'Formula 1':'formula-1', 'NASCAR':'nascar', 'MotoGP':'motogp',
         'MXGP':'mxgp', 'WWE':'wwe', 'AEW':'combat-sports', 'TNA':'tna', 'UFC':'ufc', 'Boxing':'boxing',
         'Combat Sports':'combat-sports', 'Motorsports':'motorsports'}

# Added TNA to the allowed groups
ALLOWED_GROUPS = {'NBA', 'Boxing', 'Combat Sports', 'UFC', 'AEW', 'WWE', 'TNA', 'Live'}


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
    """Format entries and remove exact duplicate URLs without grouping."""
    result = []
    seen_urls = set()
    
    for entry_raw in entries:
        entry = dict(entry_raw)
        
        # --- NEW LOGIC: Move to TNA group if the word 'tna' is in the channel name ---
        # We use a regex word boundary (\b) so it matches "TNA", but not words like "Patna"
        if re.search(r'\btna\b', entry.get('name', ''), flags=re.IGNORECASE):
            entry['group'] = 'TNA'
            
        # Only keep streams that match your requested categories
        if entry.get('group') not in ALLOWED_GROUPS:
            continue
            
        url = entry.get('url', '')
        
        # Deduplicate exact URLs 
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        entry['name'] = clean_title(entry['name'])
        entry['poster'] = entry.get('poster') or fallback_logo(entry['group'])
        
        # Date ID for EPG/M3U matching
        date = time.strftime('%Y-%m-%d', time.gmtime(entry.get('starts_at') or 0)) if entry.get('starts_at') else ''
        entry['event_id'] = f'{entry["group"]}:{event_key(entry["name"])}:{date}'
        
        provider = entry.get('provider', 'RoxieStreams')
        identity = entry.get('identity') or f'{provider}:{urlsplit(url).netloc}:{urlsplit(url).path}'
        entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        
        # Build the metadata details (provider, source tag, locale)
        details = []
        if provider.casefold() != 'roxiestreams':
            details.append(provider)
        if entry.get('source_tag'):
            details.append(entry['source_tag'])
        if entry.get('locale'):
            details.append(entry['locale'].upper())
            
        # Format the final display name
        title = entry['name'] if entry['name'].casefold().startswith(entry['group'].casefold()) else f'{entry["group"]} | {entry["name"]}'
        entry['display_name'] = title + (' — ' + ' · '.join(details) if details else '')
        
        result.append(entry)
        
    return result
