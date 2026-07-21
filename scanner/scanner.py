"""
TITAN Scanner
"""

from analysis.analyzer import Analyzer


class Scanner:

    def __init__(
        self,
        market_provider,
        analyzer: Analyzer
    ):

        self.market_provider = market_provider

        self.analyzer = analyzer


    def scan(
        self,
        stocks
    ):

        results = []


        for stock in stocks:

            series = self.market_provider.get_daily_price(
                stock
            )


            result = self.analyzer.analyze(
                stock,
                series
            )


            results.append(result)


        return results