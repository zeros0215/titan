import unittest

from tools.kis_dashboard_server import _parse_google_news_rss


class DashboardNewsTest(unittest.TestCase):
    def test_parses_title_only_news_rows_and_deduplicates(self) -> None:
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
          <item>
            <title>Sample headline - Source A</title>
            <link>https://example.com/a</link>
            <pubDate>Fri, 31 Jul 2026 01:20:00 GMT</pubDate>
            <source>Source A</source>
            <description>Article body must not be returned.</description>
          </item>
          <item>
            <title>Sample headline - Source A</title>
            <link>https://example.com/a</link>
          </item>
        </channel></rss>"""

        rows = _parse_google_news_rss(content)

        self.assertEqual(
            rows,
            [
                {
                    "title": "Sample headline - Source A",
                    "source": "Source A",
                    "published_at": "Fri, 31 Jul 2026 01:20:00 GMT",
                    "url": "https://example.com/a",
                }
            ],
        )
        self.assertNotIn("description", rows[0])


if __name__ == "__main__":
    unittest.main()
