from datetime import datetime, timedelta
import unittest

from domain.candle import Candle
from domain.candle_series import CandleSeries
from domain.enums import MarketType
from domain.stock import Stock
from market.context.context_builder import MarketContextBuilder
from market.context.market_trend import MarketTrend
from scanner.scanner import Scanner
from feature.feature_set import FeatureSet
from scoring.score_engine import ScoreEngine
from data.quality import CandleSeriesValidator


class MarketContextTest(unittest.TestCase):
    def test_builds_breadth_and_index_trends_from_market_series(self) -> None:
        kospi_up = self._series("000001", "KOSPI", 100, 120)
        kospi_down = self._series("000002", "KOSPI", 100, 90)
        kosdaq_up = self._series("000003", "KOSDAQ", 100, 130)

        context = MarketContextBuilder(lookback_days=20).build(
            [kospi_up, kospi_down, kosdaq_up]
        )

        self.assertEqual(context.kospi_trend, MarketTrend.BULL)
        self.assertEqual(context.kosdaq_trend, MarketTrend.BULL)
        self.assertAlmostEqual(context.market_strength, 2 / 3)

        score = ScoreEngine().calculate(FeatureSet(), context)
        self.assertGreater(score.context_score, 0)
        self.assertEqual(score.total_score, score.context_score)

    def test_scanner_passes_one_context_to_each_analysis(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        series = self._series("000001", "KOSPI", 100, 120)
        analyzer = _RecordingAnalyzer()
        scanner = Scanner(
            _Provider(series),
            analyzer,
            context_builder=MarketContextBuilder(),
        )

        scanner.scan([stock])

        self.assertIsNotNone(analyzer.context)
        self.assertGreater(analyzer.context.market_strength, 0)

    def test_scanner_excludes_future_candles_from_analysis_only(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        series = self._series("000001", "KOSPI", 100, 130)
        analyzer = _RecordingAnalyzer()
        scanner = Scanner(_Provider(series), analyzer)
        as_of = datetime(2026, 1, 11)

        result = scanner.scan_with_market_data([stock], as_of=as_of)

        self.assertEqual(analyzer.latest_analyzed_date, as_of)
        self.assertGreater(result.series_by_code[stock.code].latest.date, as_of)

    def test_scanner_excludes_invalid_ohlcv_before_analysis(self) -> None:
        stock = Stock("000001", "Alpha", MarketType.KOSPI)
        invalid = CandleSeries(stock, [
            Candle(datetime(2026, 1, 1), 110, 100, 90, 95, 1_000)
        ])
        analyzer = _RecordingAnalyzer()
        scanner = Scanner(
            _Provider(invalid),
            analyzer,
            quality_validator=CandleSeriesValidator(minimum_candles=1),
        )

        result = scanner.scan_with_market_data([stock])

        self.assertEqual(result.analyses, [])
        self.assertEqual(result.quality_summary.excluded_count, 1)
        self.assertIn("INVALID_OHLC", result.quality_summary.issues_by_code)

    @staticmethod
    def _series(
        code: str,
        market: str,
        start: float,
        end: float,
    ) -> CandleSeries:
        stock = Stock(code, code, MarketType(market))
        candles = []
        for index in range(21):
            close = start + (end - start) * index / 20
            candles.append(Candle(
                date=datetime(2026, 1, 1) + timedelta(days=index),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000,
            ))
        return CandleSeries(stock, candles)


class _Provider:
    def __init__(self, series: CandleSeries) -> None:
        self.series = series

    def get_daily_price(self, stock: Stock) -> CandleSeries:
        return self.series


class _RecordingAnalyzer:
    def __init__(self) -> None:
        self.context = None
        self.latest_analyzed_date = None

    def analyze(self, stock, series, context):
        self.context = context
        self.latest_analyzed_date = series.latest.date
        return object()


if __name__ == "__main__":
    unittest.main()
