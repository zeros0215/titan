"""
TITAN Pipeline
"""


class PipelineEngine:

    def __init__(

        self,

        scanner,

        filter_engine,

        ranker

    ):

        self.scanner = scanner

        self.filter = filter_engine

        self.ranker = ranker


    def execute(

        self,

        stocks

    ):

        #
        # Scan
        #
        results = self.scanner.scan(stocks)

        #
        # Filter
        #
        results = self.filter.filter(results)

        #
        # Ranking
        #
        results = self.ranker.rank(results)

        return results