import unittest
from metadata import clean_title, decorate

class MetadataTests(unittest.TestCase):
    def entry(self, url, name='Los Angeles Lakers vs Boston Celtics', provider='RoxieStreams'):
        return {'name':name,'group':'NBA','url':url,'page':'https://example.org/event','provider':provider}

    def test_titles_match_across_site_wording(self):
        self.assertEqual(clean_title('  Los Angeles Lakers at Boston Celtics '), 'Los Angeles Lakers vs Boston Celtics')
        self.assertEqual(clean_title('LA Clippers vs. Utah Jazz'), 'Los Angeles Clippers vs Utah Jazz')

    def test_duplicate_urls_removed(self):
        a = self.entry('https://example.org/a.m3u8')
        b = self.entry('https://example.org/b.m3u8', provider='RoxieStreams')
        
        output = decorate([a, a, b])
        
        self.assertEqual(len(output), 2)
        # Verify default provider (RoxieStreams) is stripped from the display name
        self.assertFalse(any('RoxieStreams' in entry['display_name'] for entry in output))
        self.assertTrue(all(e['poster'].endswith('nba.png') for e in output))
        # Verify unique IDs are generated for both unique streams
        self.assertEqual(len({e['tvg_id'] for e in output}), 2)

    def test_repeated_url_for_different_events_keeps_first(self):
        # If the same URL is passed twice (even with different names), the new logic 
        # just keeps the first one it sees and drops the duplicate URL entirely.
        output = decorate([
            self.entry('https://example.org/tsn.m3u8'), 
            self.entry('https://example.org/tsn.m3u8', 'UFC 300')
        ])
        
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]['name'], 'Los Angeles Lakers vs Boston Celtics')
        self.assertEqual(output[0]['group'], 'NBA')

if __name__ == '__main__': 
    unittest.main()
