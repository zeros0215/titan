"""
TITAN Pipeline Engine
"""

from scanner.scanner import Scanner
from ranking.ranker import Ranker
from filter.engine import FilterEngine


class PipelineEngine:

    def __init__(

        self,

        scanner: Scanner,

        filter_engine: FilterEngine,

        ranker: Ranker

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

        results = self.scanner.scan(
            stocks
        )

        #
        # Filter
        #

        results = self.filter.filter(
            results
        )

        #
        # Ranking
        #

        results = self.ranker.rank(
            results
        )

        return results