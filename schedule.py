"""Read the site's Pacific-time schedule and display Philippine time."""
from datetime import datetime
import html
import re
from zoneinfo import ZoneInfo

def start_times(text, page, links):
    result = {}
    
    # Extract all table rows from the HTML
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', text, re.I | re.S):
        
        # Look for the specific table data cell with the class 'event-start-time'
        match = re.search(r'<td\b[^>]*class=[\"\'][^\"\']*event-start-time[^\"\']*[\"\'][^>]*>(.*?)</td>', row, re.I | re.S)
        
        if not match:
            continue
            
        # Clean up the text by removing any accidental HTML tags and whitespace
        value = html.unescape(re.sub(r'<[^>]+>', '', match.group(1))).strip()
        
        try:
            # Parse the exact format found in the HTML: "October 20, 2026 12:00 PM"
            stamp = datetime.strptime(value, '%B %d, %Y %I:%M %p').replace(tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
        except ValueError:
            continue
            
        # Link the parsed timestamp to the stream URLs found in this row
        for target, label in links(row, page):
            result[(target, label)] = stamp
            
    return result

def pht_time(timestamp):
    # Convert the saved Pacific time timestamp into Philippine Standard Time
    return datetime.fromtimestamp(timestamp, ZoneInfo('Asia/Manila')).strftime('%b %d @ %I:%M %p')
