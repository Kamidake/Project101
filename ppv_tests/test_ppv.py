import unittest
from ppv_scraper import active,direct_sources,render
class PPVTests(unittest.TestCase):
    def test_time_and_continuous_category(self):
        self.assertTrue(active({}, {'always_live':1},100))
        self.assertFalse(active({'starts_at':200},{},100))
        self.assertFalse(active({'starts_at':1,'ends_at':50},{},100))
    def test_embed_and_protected_streams(self):
        self.assertEqual(direct_sources({'iframe':'https://example.org/embed'}),[])
        self.assertEqual(direct_sources({'auth':True,'m3u8':'https://example.org/a.m3u8'}),[])
        self.assertEqual(direct_sources({'m3u8':'https://example.org/a.m3u8'}),['https://example.org/a.m3u8'])
    def test_duplicate_and_alternate_feeds(self):
        a={'id':1,'name':'A vs B','group':'Soccer','url':'https://example.org/a.m3u8'}
        b=dict(a,url='https://example.org/b.m3u8')
        output=render([a,a,b])
        self.assertEqual(output.count('#EXTINF:'),2)
        self.assertIn('Feed 1',output); self.assertIn('Feed 2',output)
        self.assertEqual(output,render([b,a]))
