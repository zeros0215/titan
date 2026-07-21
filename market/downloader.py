"""
Market Downloader
"""

from abc import ABC
from abc import abstractmethod


class MarketDownloader(ABC):

    @abstractmethod
    def download(self):

        pass