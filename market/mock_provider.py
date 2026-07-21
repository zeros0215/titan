"""
Mock Downloader
"""


from market.downloader import MarketDownloader


class MockMarketDownloader(

    MarketDownloader

):

    def download(self):

        return [

            {
                "code": "005930",
                "name": "Samsung Electronics",
                "market": "KOSPI"
            },

            {
                "code": "000660",
                "name": "SK Hynix",
                "market": "KOSPI"
            },

            {
                "code": "035420",
                "name": "NAVER",
                "market": "KOSPI"
            },

            {
                "code": "005380",
                "name": "Hyundai Motor",
                "market": "KOSPI"
            },

            {
                "code": "105560",
                "name": "KB Financial",
                "market": "KOSPI"
            },

            {
                "code": "068270",
                "name": "Celltrion",
                "market": "KOSDAQ"
            }

        ]