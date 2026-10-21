"""Read the site's Pacific-time schedule and display Philippine time."""
from datetime import datetime
import html
import re
from zoneinfo import ZoneInfo


def start_times(text, page, links):
    result = {}
    
    # 1. Find all table rows
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', text, re.I | re.S):
        
        # 2. Strip ALL HTML tags from the row to get just the raw text
        clean_text = html.unescape(re.sub(r'<[^>]+>', ' ', row)).strip()
        
        # 3. Hunt for ANY text that matches: Month DD, YYYY HH:MM AM/PM
        # This ignores classes and just looks for the actual date format.
        date_match = re.search(r'([A-Z][a-z]+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)', clean_text, re.I)
        
        if not date_match:
            continue
            
        value = " ".join(date_match.group(1).split()) # Clean up any weird spacing
        
        try:
            # Try parsing full month name (e.g., October 20, 2026 12:00 PM)
            stamp = datetime.strptime(value, '%B %d, %Y %I:%M %p').replace(tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
        except ValueError:
            try:
                # Try parsing abbreviated month name just in case (e.g., Oct 20, 2026 12:00 PM)
                stamp = datetime.strptime(value, '%b %d, %Y %I:%M %p').replace(tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
            except ValueError:
                continue
                
        for target, label in links(row, page):
            result[(target, label)] = stamp
            
    return result


def pht_time(timestamp):
    return datetime.fromtimestamp(timestamp, ZoneInfo('Asia/Manila')).strftime('%b %d, %I:%M %p PHT')
