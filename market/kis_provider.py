"""
KIS Market Downloader
"""

from market.downloader import MarketDownloader

from broker.kis.session import KisSession


class KisMarketDownloader(

    MarketDownloader

):

    def __init__(self):

        self.session = KisSession()

    def download(self):

        """
        종목 목록 다운로드

        (현재는 추후 구현)

        """

        raise NotImplementedError(
            "KIS Downloader is not implemented."
        )