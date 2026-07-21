from screener.filters.history import HistoryFilter

from screener.filters.price import PriceFilter

from screener.filters.volume import VolumeFilter

from screener.filters.liquidity import LiquidityFilter


class FilterEngine:

    def __init__(self):

        self.filters = [

            HistoryFilter(),

            PriceFilter(),

            VolumeFilter(),

            LiquidityFilter()

        ]

    def check(self, series):

        for f in self.filters:

            if not f.check(series):

                return False

        return True