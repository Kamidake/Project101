import unittest
from schedule import start_times
from scraper import internal_links, collect_roxie
from metadata import decorate

class ScheduleTests(unittest.TestCase):
    def test_schedule_is_ignored_and_not_appended_to_title(self):
        page = 'https://roxiestreams.info/nba-streams-1'
        row = '<tr><td><a href="/nba-streams-1">Team A vs Team B</a></td><td class="event-start-time">October 20, 2026 12:00 PM</td></tr>'
        
        candidates, _, _ = collect_roxie({'https://roxiestreams.info/nba': row, page: 'https://example.test/live.m3u8'}, {})
        
        # Decorate the extracted entries
        entry = decorate(next(iter(candidates.values())))[0]
        
        # The title test now expects ONLY the clean event title.
        # It should not contain the time or the '@' symbol.
        self.assertEqual(entry['display_name'], 'Team A vs Team B')
        self.assertNotIn('@', entry['display_name'])

    def test_missing_or_invalid_schedule_does_not_invent_time(self):
        # start_times should safely return an empty dict for dummy or invalid text
        self.assertEqual(start_times('<tr>Time TBA</tr>', 'https://roxiestreams.info/', internal_links), {})
