"""Consistent IPTV titles, category artwork, and feed labels."""
import hashlib
import html
import re
import time
import unicodedata
from urllib.parse import urlsplit
from datetime import datetime, timedelta
try:
    import zoneinfo
except ImportError:
    zoneinfo = None

LOGO_BASE = 'https://raw.githubusercontent.com/Kamidake/Project101/main/assets/logos/'

GROUPS = {'nfl':'NFL', 'redzone':'NFL', 'nba':'NBA', 'wnba':'WNBA', 'nhl':'NHL',
          'mlb':'MLB', 'soccer':'Soccer', 'f1':'Formula 1', 'nascar':'NASCAR',
          'motogp':'MotoGP', 'mxgp':'MXGP', 'wwe':'WWE', 'aew':'AEW', 'tna':'TNA', 'ufc':'UFC',
          'boxing':'Boxing', 'fighting':'Combat Sports', 'motorsports':'Motorsports'}

LOGOS = {'NFL':'nfl', 'NBA':'nba', 'WNBA':'wnba', 'NHL':'nhl', 'MLB':'mlb',
         'Soccer':'soccer', 'Formula 1':'formula-1', 'NASCAR':'nascar', 'MotoGP':'motogp',
         'MXGP':'mxgp', 'WWE':'wwe', 'AEW':'combat-sports', 'TNA':'tna', 'UFC':'ufc', 'Boxing':'boxing',
         'Combat Sports':'combat-sports', 'Motorsports':'motorsports'}

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


def process_schedule_time(time_str):
    """Parses time and returns a formatted display string, XMLTV times, and the datetime object."""
    if not time_str or not zoneinfo:
        return time_str, None, None, None
        
    time_str = " ".join(time_str.split())
    
    try:
        dt = datetime.strptime(time_str, "%B %d, %Y %I:%M %p")
        
        # --- Add 3 hours to the scheduled time ---
        dt += timedelta(hours=3)
        
        dt_et = dt.replace(tzinfo=zoneinfo.ZoneInfo("America/New_York"))
        dt_ph = dt_et.astimezone(zoneinfo.ZoneInfo("Asia/Manila"))
        
        # 1. Display String (e.g. "Oct 14 @ 09:45 AM")
        display = dt_ph.strftime("%b %d @ %I:%M %p")
        
        # 2. XMLTV timestamps (Format: YYYYMMDDHHMMSS +0800)
        xmltv_start = dt_ph.strftime("%Y%m%d%H%M00 +0800")
        xmltv_stop = (dt_ph + timedelta(hours=3)).strftime("%Y%m%d%H%M00 +0800") # Default duration 3 hours
        
        # Return dt_ph so we can calculate if it's currently live
        return display, xmltv_start, xmltv_stop, dt_ph
    except ValueError:
        return re.sub(r',? \d{4}', '', time_str), None, None, None


def decorate(entries):
    """Format entries and remove exact duplicate URLs without grouping."""
    result = []
    seen_urls = set()
    
    # Get current time in Manila to check against stream schedules
    now_ph = datetime.now(zoneinfo.ZoneInfo("Asia/Manila")) if zoneinfo else datetime.now()
    
    for entry_raw in entries:
        entry = dict(entry_raw)
        
        page_url = str(entry.get('page', '')).casefold()
        referrer_url = str(entry.get('referrer', '')).casefold()
        
        if 'floracing' in page_url or 'floracing' in referrer_url:
            continue
        
        if 'ncaa' in page_url or 'ncaa' in referrer_url:
            continue

        if re.search(r'\btna\b', entry.get('name', ''), flags=re.IGNORECASE):
            entry['group'] = 'TNA'
        if re.search(r'\baew\b', entry.get('name', ''), flags=re.IGNORECASE):
            entry['group'] = 'AEW'
            
        if entry.get('group') not in ALLOWED_GROUPS:
            continue
            
        url = entry.get('url', '')
        
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        entry['name'] = clean_title(entry['name'])
        
        # Set default logo first
        entry['poster'] = entry.get('poster') or fallback_logo(entry['group'])
        
        date = time.strftime('%Y-%m-%d', time.gmtime(entry.get('starts_at') or 0)) if entry.get('starts_at') else ''
        entry['event_id'] = f'{entry["group"]}:{event_key(entry["name"])}:{date}'
        
        # --- Handle Time, XMLTV Data, and Live Logo Swap ---
        entry['base_name'] = entry['name'] # Keep original name for the EPG Title
        if entry.get('start_time'):
            display_time, xmltv_start, xmltv_stop, dt_start = process_schedule_time(entry['start_time'])
            
            if display_time:
                # Appends the time using the format: Event Name | Oct 16 @ 07:30 AM
                entry['name'] = f"{entry['name']} | {display_time}"
            if xmltv_start:
                entry['xmltv_start'] = xmltv_start
                entry['xmltv_stop'] = xmltv_stop
                
            # --- DYNAMIC LIVE LOGO LOGIC ---
            if dt_start:
                dt_stop = dt_start + timedelta(hours=3) # Assuming 3 hour duration as defined earlier
                if dt_start <= now_ph <= dt_stop:
                    # Look up the base filename for this group (e.g., 'nba', 'ufc')
                    base_logo = LOGOS.get(entry['group'], 'live')
                    # Construct the URL: e.g., https://.../assets/logos/nba-live.png
                    entry['poster'] = f"{LOGO_BASE}{base_logo}-live.png"

        provider = entry.get('provider', 'RoxieStreams')
        identity = entry.get('identity') or f'{provider}:{urlsplit(url).netloc}:{urlsplit(url).path}'
        
        entry['tvg_id'] = 'lennon.' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        
        details = []
        if provider.casefold() != 'roxiestreams':
            details.append(provider)
        if entry.get('source_tag'):
            details.append(entry['source_tag'])
        if entry.get('locale'):
            details.append(entry['locale'].upper())
            
        title = entry['name'] if entry['name'].casefold().startswith(entry['group'].casefold()) else f'{entry["group"]} | {entry["name"]}'
        entry['display_name'] = title + (' — ' + ' · '.join(details) if details else '')
        
        result.append(entry)
        
    return result
