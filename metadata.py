"""Consistent IPTV titles, category artwork, and feed labels (NBA, Wrestling, UFC, Boxing, Combat Sports Only)."""
from collections import defaultdict
import hashlib
import html
import re
import time
import unicodedata
from urllib.parse import urlsplit

LOGO_BASE = 'https://raw.githubusercontent.com/Zer0Spce/ZeroStreams/main/assets/logos/'

# Filter & map exclusively to NBA, Wrestling, UFC, Boxing, and Combat Sports
GROUPS = {
    'nba': 'NBA',
    'wwe': 'WWE',
    'wrestling': 'Wrestling',
    'aew': 'Wrestling',
    'ufc': 'UFC',
    'mma': 'UFC',
    'boxing': 'Boxing',
    'fighting': 'Combat Sports',
    'combat-sports': 'Combat Sports',
    'combat': 'Combat Sports'
}

LOGOS = {
    'NBA': 'nba',
    'WWE': 'wwe',
    'Wrestling': 'wwe', 
    'UFC': 'ufc',
    'Boxing': 'boxing',
    'Combat Sports': 'combat-sports'
}

TARGET_GROUPS = set(GROUPS.values())


def clean_title(value):
    value = ' '.join(html.unescape(str(value)).split())
    value = re.sub(r'\bvs\.?\s*', 'vs ', value, flags=re.I)
    value = re.sub(r'\s+at\s+', ' vs ', value, flags=re.I)
    # Common NBA cleanups
    value = re.sub(r'\bLA Clippers\b', 'Los Angeles Clippers', value)
    value = re.sub(r'\bLA Lakers\b', 'Los Angeles Lakers', value)
    value = re.sub(r'\bGS Warriors\b', 'Golden State Warriors', value)
    return value.strip()


def event_key(name):
    text = unicodedata.normalize('NFKD', clean_title(name)).casefold()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def roxie_group(page):
    slug = urlsplit(page).path.strip('/').split('-')[0].lower()
    return GROUPS.get(slug, None)


def fallback_logo(group):
    # Default to live if one of the targeted logos happens to miss
    return LOGO_BASE + LOGOS.get(group, 'live') + '.png'


def is_target_entry(entry):
    """Check whether a stream entry belongs to NBA, Wrestling, UFC, Boxing, or Combat Sports."""
    # 1. Check if an explicit group is already assigned and matches our targets
    group = entry.get('group')
    if group in TARGET_GROUPS:
        return True

    # 2. Check the page URL slug
    if entry.get('page') and roxie_group(entry['page']) is not None:
        return True

    # 3. Fallback: Check if the title explicitly mentions key leagues/sports
    name = entry.get('name', '').lower()
    target_keywords = ('nba', 'wwe', 'aew', 'wrestling', 'ufc', 'mma', 'boxing', 'fighting', 'combat')
    return any(re.search(rf'\b{re.escape(k)}\b', name) for k in target_keywords)


def decorate(entries):
    """Filter for target categories, dedupe exact URLs, merge events, and number distinct feeds."""
    # Step 1: Filter out non-target entries immediately
    target_entries = []
    for raw in entries:
        item = dict(raw)
        # Check if the missing/mismatched group can be mapped via URL
        if not item.get('group') or item['group'] not in TARGET_GROUPS:
            detected_group = roxie_group(item.get('page', ''))
            if detected_group:
                item['group'] = detected_group

        if is_target_entry(item):
            # Fallback label if the regex matched but a group wasn't assigned
            if not item.get('group'):
                item['group'] = 'Combat Sports' 
            target_entries.append(item)

    # Step 2: Dedupe exact stream URLs
    by_url = defaultdict(list)
    for entry in target_entries:
        by_url[entry['url']].append(entry)

    unique = []
    for url, aliases in sorted(by_url.items()):
        aliases.sort(key=lambda e: (e.get('provider', 'RoxieStreams'), e.get('page', ''), e['name']))
        entry = aliases[0]
        names = {event_key(e['name']) for e in aliases}
        entry['provider'] = ' + '.join(sorted({e.get('provider', 'RoxieStreams') for e in aliases}))

        if len(names) > 1:
            channel = urlsplit(url).path.rsplit('/', 1)[-1].removesuffix('.m3u8')
            entry['name'] = channel.upper() + ' — Shared Feed'
            categories = {alias['group'] for alias in aliases}
            entry['group'] = next(iter(categories)) if len(categories) == 1 else 'Shared Target Channels'
            entry['poster'] = ''
        else:
            entry['name'] = clean_title(entry['name'])

        entry['poster'] = entry.get('poster') or fallback_logo(entry['group'])
        date = time.strftime('%Y-%m-%d', time.gmtime(entry.get('starts_at') or 0)) if entry.get('starts_at') else ''
        entry['event_id'] = f'{entry["group"]}:{event_key(entry["name"])}:{date}'
        identity = entry.get('identity') or f'{entry["provider"]}:{urlsplit(url).netloc}:{urlsplit(url).path}'
        entry['tvg_id'] = 'zerostreams.' + hashlib.sha256(identity.encode()).hexdigest()[:16]
        unique.append(entry)

    # Step 3: Group feeds by matching event/fight/game
    groups = defaultdict(list)
    for entry in unique:
        groups[entry['event_id']].append(entry)

    result = []
    for key in sorted(groups):
        feeds = sorted(groups[key], key=lambda e: (e['provider'], e.get('source_tag', ''), e['url']))
        for index, entry in enumerate(feeds, 1):
            details = [f'Feed {index}'] if len(feeds) > 1 else []
            details.extend(provider for provider in entry['provider'].split(' + ') if provider.casefold() != 'roxiestreams')
            if entry.get('source_tag'):
                details.append(entry['source_tag'])
            if entry.get('locale'):
                details.append(entry['locale'].upper())

            title = entry['name'] if entry['name'].casefold().startswith(entry['group'].casefold()) else f'{entry["group"]} | {entry["name"]}'
            entry['display_name'] = title + (' — ' + ' · '.join(details) if details else '')
            result.append(entry)

    return result
