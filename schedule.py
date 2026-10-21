"""Read the site's Pacific-time schedule and display Philippine time."""
from datetime import datetime
import html
import re
from zoneinfo import ZoneInfo


def start_times(text, page, links):
    result = {}
    current_year = datetime.now().year
    
    # Split the HTML by generic blocks (Table rows, list items, or divisions)
    chunks = re.split(r'<(?:tr|li|div)\b', text, flags=re.I)
    
    for chunk in chunks:
        # Re-add the opening bracket so the HTML parser doesn't break
        chunk = '<div ' + chunk 
        
        # 1. Check if there are any stream links in this block
        row_links = list(links(chunk, page))
        if not row_links:
            continue
            
        # Strip HTML to get plain text
        clean_text = html.unescape(re.sub(r'<[^>]+>', ' ', chunk)).strip()
        
        # 2. Look for ANY date format (With or without the year, full or abbreviated month)
        # Matches: "Oct 21, 2026 12:00 PM", "October 21 12:00 PM", etc.
        date_match = re.search(r'([a-zA-Z]{3,9})\s+(\d{1,2})(?:,?\s+(\d{4}))?\s+(\d{1,2}:\d{2}\s+[AP]M)', clean_text, re.I)
        
        if not date_match:
            continue
            
        month, day, year, time_str = date_match.groups()
        
        # If the website forgot the year, we add the current year automatically
        year = year or str(current_year)
        
        # Standardize the format to: "Oct 21, 2026 12:00 PM"
        value = f"{month[:3].capitalize()} {day}, {year} {time_str}"
        
        try:
            # Parse the standardized date format
            stamp = datetime.strptime(value, '%b %d, %Y %I:%M %p').replace(tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
            
            # Map the parsed time to every link found in this HTML block
            for target, label in row_links:
                result[(target, label)] = stamp
        except ValueError:
            continue
            
    return result


def pht_time(timestamp):
    return datetime.fromtimestamp(timestamp, ZoneInfo('Asia/Manila')).strftime('%b %d, %I:%M %p PHT')
