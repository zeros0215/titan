from datetime import datetime

from backtest.engine.backtest_engine import BacktestEngine
from backtest.engine.selection_engine import SelectionEngine
from backtest.price_resolver import CandlePriceResolver
from ranking.ranking_engine import RankingEngine
from report.report_generator import ReportGenerator
from runner.titan_run_result import TitanRunResult
from runner.selection_run_result import SelectionRunResult
from validation.validator import Validator
from domain.enums import MarketType


class TitanRunner:
    """Coordinates the V1 selection workflow; business logic remains in each component."""

    def __init__(
        self,
        stock_repository,
        scanner,
        ranking_engine: RankingEngine,
        selection_engine: SelectionEngine,
        backtest_engine: BacktestEngine,
        validator: Validator,
        report_generator: ReportGenerator,
        selection_repository=None,
        price_resolver: CandlePriceResolver | None = None,
        filter_engine=None,
        candle_repository=None,
        benchmark_provider=None,
        observation_repository=None,
        observation_policy=None,
        quality_repository=None,
        universe_repository=None,
        quality_quarantine_policy=None,
    ) -> None:
        self.stock_repository = stock_repository
        self.scanner = scanner
        self.ranking_engine = ranking_engine
        self.selection_engine = selection_engine
        self.backtest_engine = backtest_engine
        self.validator = validator
        self.report_generator = report_generator
        self.selection_repository = selection_repository
        self.price_resolver = price_resolver or CandlePriceResolver()
        self.filter_engine = filter_engine
        self.candle_repository = candle_repository
        self.benchmark_provider = benchmark_provider
        self.observation_repository = observation_repository
        self.observation_policy = observation_policy
        self.quality_repository = quality_repository
        self.universe_repository = universe_repository
        self.quality_quarantine_policy = quality_quarantine_policy

    def run(
        self,
        selection_date: datetime,
        evaluation_date: datetime,
        holding_days: int,
        top_n: int = 5,
        success_return: float = 0.0,
        benchmark_returns: dict[str, float] | None = None,
    ) -> TitanRunResult:
        selection_run = self.select(selection_date, top_n)
        if benchmark_returns is None and self.benchmark_provider is not None:
            benchmark_returns = self.benchmark_provider.get_returns(
                {
                    selection.analysis.market
                    for selection in selection_run.selections
                    if selection.analysis.market
                    in (MarketType.KOSPI, MarketType.KOSDAQ)
                },
                selection_date,
                evaluation_date,
            )
        prices = self.price_resolver.resolve(
            selection_run.selections,
            selection_run.series_by_code,
            evaluation_date,
        )
        backtest = self.backtest_engine.run(
            selections=selection_run.selections,
            evaluation_date=evaluation_date,
            holding_days=holding_days,
            selection_prices=prices.selection_prices,
            evaluation_prices=prices.evaluation_prices,
            benchmark_returns=benchmark_returns,
        )
        validation = self.validator.validate(
            backtest,
            success_return=success_return,
        )
        report_markdown = self.report_generator.generate_markdown(validation)

        return TitanRunResult(
            ranking=selection_run.ranking,
            selections=selection_run.selections,
            backtest=backtest,
            validation=validation,
            report_markdown=report_markdown,
        )

    def select(
        self,
        selection_date: datetime,
        top_n: int = 5,
    ) -> SelectionRunResult:
        universe_snapshot = (
            self.stock_repository.get_as_of(selection_date)
            if hasattr(self.stock_repository, "get_as_of")
            else None
        )
        stocks = (
            universe_snapshot.stocks
            if universe_snapshot is not None
            else self.stock_repository.get_all()
        )
        scan = self.scanner.scan_with_market_data(
            stocks,
            as_of=selection_date,
        )
        quality_eligible = (
            self.quality_quarantine_policy.filter(
                scan.analyses, selection_date
            )
            if self.quality_quarantine_policy is not None
            else scan.analyses
        )
        analyses = (
            self.filter_engine.filter(quality_eligible)
            if self.filter_engine is not None
            else quality_eligible
        )
        observations = (
            self.observation_policy.select(
                quality_eligible, selection_date
            )
            if self.observation_policy is not None
            else []
        )
        ranking = self.ranking_engine.rank(analyses)
        selections = self.selection_engine.select(
            ranking,
            selected_date=selection_date,
            top_n=top_n,
        )
        snapshot_path = (
            self.selection_repository.save(selections, selected_at=selection_date)
            if self.selection_repository is not None
            else None
        )
        observation_snapshot_path = (
            self.observation_repository.save(
                observations,
                selected_at=selection_date,
            )
            if self.observation_repository is not None
            else None
        )
        quality_report_path = (
            self.quality_repository.save(
                selection_date,
                scan.quality_summary,
            )
            if (
                self.quality_repository is not None
                and scan.quality_summary is not None
            )
            else None
        )
        universe_report_path = (
            self.universe_repository.save(universe_snapshot)
            if (
                self.universe_repository is not None
                and universe_snapshot is not None
            )
            else None
        )
        if self.candle_repository is not None:
            self.candle_repository.save_many({
                selection.code: scan.series_by_code[selection.code]
                for selection in selections + observations
                if selection.code in scan.series_by_code
            })
        return SelectionRunResult(
            ranking=ranking,
            selections=selections,
            series_by_code=scan.series_by_code,
            snapshot_path=snapshot_path,
            observations=observations,
            observation_snapshot_path=observation_snapshot_path,
            quality_summary=scan.quality_summary,
            quality_report_path=quality_report_path,
            universe_snapshot=universe_snapshot,
            universe_report_path=universe_report_path,
            fetch_failures=scan.fetch_failures,
        )
