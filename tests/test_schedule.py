import unittest
from schedule import start_times, pht_time
from scraper import internal_links, collect_roxie
from metadata import decorate

class ScheduleTests(unittest.TestCase):
    def test_pacific_to_pht_next_day_and_event_title(self):
        page = 'https://roxiestreams.info/nba-streams-1'
        row = '<tr><td><a href="/nba-streams-1">Team A vs Team B</a></td><td class="event-start-time">October 20, 2026 12:00 PM</td></tr>'
        result = start_times(row, 'https://roxiestreams.info/nba', internal_links)
        stamp = result[(page, 'Team A vs Team B')]
        
        # Test now expects the time formatted with the @ symbol
        self.assertEqual(pht_time(stamp), 'Oct 21 @ 03:00 AM')
        
        candidates, _, _ = collect_roxie({'https://roxiestreams.info/nba': row, page: 'https://example.test/live.m3u8'}, {})
        entry = decorate(next(iter(candidates.values())))[0]
        
        # Title test now expects the schedule with the @ symbol
        self.assertIn('Oct 21 @ 03:00 AM', entry['display_name'])

    def test_missing_or_invalid_schedule_does_not_invent_time(self):
        self.assertEqual(start_times('<tr>Time TBA</tr>', 'https://roxiestreams.info/', internal_links), {})
