import unittest
from metadata import clean_title, decorate

class MetadataTests(unittest.TestCase):
    def entry(self, url, name='Los Angeles Lakers vs Boston Celtics', provider='RoxieStreams'):
        return {'name':name,'group':'NBA','url':url,'page':'https://example.org/event','provider':provider}

    def test_titles_match_across_site_wording(self):
        self.assertEqual(clean_title('  Los Angeles Lakers at Boston Celtics '), 'Los Angeles Lakers vs Boston Celtics')
        self.assertEqual(clean_title('LA Clippers vs. Utah Jazz'), 'Los Angeles Clippers vs Utah Jazz')

    def test_duplicate_urls_removed_and_alternates_numbered(self):
        a=self.entry('https://example.org/a.m3u8')
        b=self.entry('https://example.org/b.m3u8', provider='RoxieStreams')
        output=decorate([a,a,b])
        self.assertEqual(len(output),2)
        self.assertFalse(any('RoxieStreams' in entry['display_name'] for entry in output))
        self.assertTrue(all(e['poster'].endswith('nba.png') for e in output))
        self.assertIn('Feed 1',output[0]['display_name'])
        self.assertIn('Feed 2',output[1]['display_name'])
        self.assertEqual(len({e['tvg_id'] for e in output}),2)
        self.assertEqual(output,decorate([b,a,a]))

    def test_repeated_url_for_different_events_is_not_mislabeled(self):
        output=decorate([self.entry('https://example.org/tsn.m3u8'), self.entry('https://example.org/tsn.m3u8','UFC 300')])
        self.assertEqual(output[0]['name'],'TSN — Shared Feed')
        self.assertEqual(output[0]['group'],'NBA')

if __name__=='__main__': unittest.main()
