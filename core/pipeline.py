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

        results = self.scanner.scan(stocks)

        print(
            "SCAN RESULT:",
            len(results)
        )


        results = self.filter.filter(results)

        print(
            "FILTER RESULT:",
            len(results)
        )


        results = self.ranker.rank(results)

        print(
            "RANK RESULT:",
            len(results)
        )
        return results