"""
TITAN Scanner
"""

from analysis.analyzer import Analyzer
from broker.provider import load_daily_prices
from datetime import datetime, timedelta
from market.context.context_builder import MarketContextBuilder
from scanner.scan_result import ScanResult
from data.quality import (
    CandleSeriesValidator,
    DataQualityIssue,
    DataQualitySeverity,
    DataQualitySummary,
)


class Scanner:

    def __init__(

        self,

        market_provider,

        analyzer: Analyzer,
        context_builder: MarketContextBuilder | None = None,
        quality_validator: CandleSeriesValidator | None = None,

    ):

        self.market_provider = market_provider

        self.analyzer = analyzer
        self.context_builder = context_builder
        self.quality_validator = quality_validator or CandleSeriesValidator(
            minimum_candles=1
        )


    def scan(

        self,

        stocks,
        as_of: datetime | None = None,

    ):

        return self.scan_with_market_data(stocks, as_of=as_of).analyses

    def scan_with_market_data(
        self,
        stocks,
        as_of: datetime | None = None,
    ) -> ScanResult:
        now = datetime.now()
        analysis_date = as_of or now
        # Fetch all currently available candles for caching/backtesting, then
        # apply the point-in-time cutoff only to the analysis view below.
        fetch_end_date = max(analysis_date, now)
        start_date = analysis_date - timedelta(days=365)
        raw_series_by_stock = []
        fetch_failures = {}
        for stock in stocks:
            try:
                series = load_daily_prices(
                    self.market_provider,
                    stock,
                    start_date,
                    fetch_end_date,
                )
                raw_series_by_stock.append((stock, series))
            except Exception as error:
                fetch_failures[stock.code] = (
                    f"{type(error).__name__}: {error}"
                )
        quality_results = {
            stock.code: self.quality_validator.validate(
                series.until(as_of) if as_of is not None else series
            )
            for stock, series in raw_series_by_stock
        }
        analysis_series_by_stock = [
            (stock, quality_results[stock.code].series)
            for stock, _ in raw_series_by_stock
            if quality_results[stock.code].is_valid
        ]
        context = (
            self.context_builder.build(
                [series for _, series in analysis_series_by_stock]
            )
            if self.context_builder is not None
            else None
        )
        results = []

        for stock, series in analysis_series_by_stock:

            result = self.analyzer.analyze(

                stock,
                series,
                context,

            )

            results.append(result)

        quality_summary = DataQualitySummary.from_results(quality_results)
        if fetch_failures:
            fetch_issues = {
                code: [
                    DataQualityIssue(
                        "FETCH_ERROR",
                        DataQualitySeverity.ERROR,
                        message,
                    )
                ]
                for code, message in fetch_failures.items()
            }
            quality_summary = DataQualitySummary(
                total_count=quality_summary.total_count + len(fetch_failures),
                valid_count=quality_summary.valid_count,
                warning_count=quality_summary.warning_count,
                excluded_count=(
                    quality_summary.excluded_count + len(fetch_failures)
                ),
                issues_by_code={
                    **quality_summary.issues_by_code,
                    "FETCH_ERROR": len(fetch_failures),
                },
                issues_by_stock={
                    **quality_summary.issues_by_stock,
                    **fetch_issues,
                },
            )
        return ScanResult(
            analyses=results,
            series_by_code={
                stock.code: series
                for stock, series in raw_series_by_stock
            },
            quality_summary=quality_summary,
            fetch_failures=fetch_failures,
        )
