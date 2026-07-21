"""
TITAN Dependency Container
"""

from broker.factory import ProviderFactory

from indicators.calculator import IndicatorCalculator
from scoring.engine import ScoreEngine
from analysis.analyzer import Analyzer

from repository.stock_repository import StockRepository
from scanner.scanner import Scanner

from filter.engine import FilterEngine
from ranking.ranker import Ranker

from core.pipeline import PipelineEngine
from report.json_reporter import JsonReporter
from storage.report_repository import ReportRepository

class Container:

    def __init__(self):

        #
        # Market Provider
        #
        self.provider = ProviderFactory.create()


        #
        # Engines
        #
        self.indicator_calculator = IndicatorCalculator()

        self.score_engine = ScoreEngine()


        #
        # Analyzer
        #
        self.analyzer = Analyzer(
            self.indicator_calculator,
            self.score_engine
        )


        #
        # Repository
        #
        self.stock_repository = StockRepository()


        #
        # Scanner
        #
        self.scanner = Scanner(
            self.provider,
            self.analyzer
        )


        #
        # Filter
        #
        self.filter_engine = FilterEngine()


        #
        # Ranker
        #
        self.ranker = Ranker()


        #
        # Pipeline
        #
        self.pipeline = PipelineEngine(
            self.scanner,
            self.filter_engine,
            self.ranker
        )

        self.json_reporter = JsonReporter()

        self.report_repository = ReportRepository()        