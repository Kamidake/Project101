"""Read the site's Pacific-time schedule and display Philippine time."""
from datetime import datetime
import html
import re
from zoneinfo import ZoneInfo


def start_times(text, page, links):
    result = {}
    
    # 1. Check if we find ANY table rows on the page
    rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', text, re.I | re.S)
    if rows and 'streams-' not in page:  # Ignore individual player pages
        print(f"DEBUG: Found {len(rows)} table rows on {page}", flush=True)
        
    for row in rows:
        # 2. Check if the 'event-start-time' class still exists
        match = re.search(r'<td\b[^>]*class=[\"\'][^\"\']*event-start-time[^\"\']*[\"\'][^>]*>(.*?)</td>', row, re.I | re.S)
        if not match:
            continue
            
        value = html.unescape(re.sub('<[^>]+>', '', match[1])).strip()
        
        try:
            # 3. Check if the date format changed
            stamp = datetime.strptime(value, '%B %d, %Y %I:%M %p').replace(tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
        except ValueError:
            print(f"SCHEDULE ERROR on {page}: Date format changed. Found: '{value}'", flush=True)
            continue
            
        row_links = list(links(row, page))
        if not row_links:
            print(f"SCHEDULE ERROR on {page}: Found date '{value}' but no clickable link in this row!", flush=True)
            
        for target, label in row_links:
            result[(target, label)] = stamp
            
    if result:
        print(f"DEBUG: Successfully matched {len(result)} scheduled events on {page}", flush=True)
        
    return result


def pht_time(timestamp):
    return datetime.fromtimestamp(timestamp, ZoneInfo('Asia/Manila')).strftime('%b %d, %I:%M %p PHT')
