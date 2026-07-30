from datetime import datetime, timedelta
from broker.provider import load_daily_prices

from analysis.analysis_result import AnalysisResult
from backtest.engine.backtest_engine import BacktestEngine
from backtest.model.selection import Selection
from backtest.model.selection_snapshot import SelectionSnapshot
from backtest.price_resolver import CandlePriceResolver
from decision.decision_result import DecisionResult
from decision.decision_type import DecisionType
from domain.enums import MarketType
from domain.stock import Stock
from feature.feature import Feature
from feature.feature_set import FeatureSet
from feature.feature_type import FeatureType
from prediction.prediction_grade import PredictionGrade
from prediction.prediction_result import PredictionResult
from report.report_generator import ReportGenerator
from runner.deferred_validation_result import DeferredValidationResult
from scoring.score_result import ScoreResult
from validation.validator import Validator
from validation.validation_record import ValidationRecord
from repository.candle_repository import CandleRepository
from market.context.market_context import MarketContext
from market.context.market_trend import MarketTrend
from backtest.trading_session_resolver import TradingSessionResolver


class DeferredValidationRunner:
    """Evaluates saved selections when their evaluation date has arrived."""

    def __init__(
        self,
        selection_repository,
        market_provider,
        backtest_engine: BacktestEngine,
        validator: Validator,
        report_generator: ReportGenerator,
        price_resolver: CandlePriceResolver | None = None,
        candle_repository=None,
        validation_repository=None,
        benchmark_provider=None,
    ) -> None:
        self.selection_repository = selection_repository
        self.market_provider = market_provider
        self.backtest_engine = backtest_engine
        self.validator = validator
        self.report_generator = report_generator
        self.price_resolver = price_resolver or CandlePriceResolver()
        self.candle_repository = candle_repository
        self.validation_repository = validation_repository
        self.benchmark_provider = benchmark_provider

    def run(
        self,
        selected_at: datetime,
        evaluation_date: datetime,
        holding_days: int,
        success_return: float = 0.0,
        trade_time: str | None = None,
        sell_time: str | None = None,
        market_trend_filter: bool = False,
        benchmark_returns: dict[str, float] | None = None,
    ) -> DeferredValidationResult:
        if holding_days <= 0:
            raise ValueError("holding_days must be greater than zero")
        if evaluation_date <= selected_at:
            raise ValueError("evaluation_date must be after selected_at")

        selections = self._load_selections(selected_at)
        if benchmark_returns is None and self.benchmark_provider is not None:
            benchmark_returns = self.benchmark_provider.get_returns(
                {
                    selection.analysis.market
                    for selection in selections
                    if selection.analysis.market
                    in (MarketType.KOSPI, MarketType.KOSDAQ)
                },
                selected_at,
                evaluation_date,
            )
        series_by_code = self._fetch_series(
            selections,
            selected_at,
            evaluation_date,
        )
        return self._evaluate(
            selections,
            series_by_code,
            selected_at,
            evaluation_date,
            holding_days,
            success_return,
            trade_time,
            sell_time,
            market_trend_filter,
            benchmark_returns,
        )

    def run_horizons(
        self,
        selected_at: datetime,
        as_of: datetime,
        holding_days: list[int] | tuple[int, ...] = (5, 10, 20, 40),
        success_return: float = 0.0,
        trade_time: str | None = None,
        sell_time: str | None = None,
        market_trend_filter: bool = False,
    ) -> dict[int, DeferredValidationResult]:
        """Validate one snapshot at multiple observed trading-session horizons."""
        if as_of <= selected_at:
            raise ValueError("as_of must be after selected_at")
        selections = self._load_selections(selected_at)
        series_by_code = self._fetch_series(selections, selected_at, as_of)
        evaluation_dates = TradingSessionResolver.resolve(
            series_by_code,
            selected_at,
            holding_days,
            as_of,
        )
        return {
            days: self._evaluate(
                selections,
                series_by_code,
                selected_at,
                evaluation_date,
                days,
                success_return,
                trade_time,
                sell_time,
                market_trend_filter,
                None,
            )
            for days, evaluation_date in evaluation_dates.items()
        }

    def _load_selections(self, selected_at: datetime) -> list[Selection]:
        snapshots = self.selection_repository.load(selected_at)
        if not snapshots and not self.selection_repository.exists(selected_at):
            raise FileNotFoundError(
                f"no selection snapshot found for {selected_at.isoformat()}"
            )
        return [self._to_selection(snapshot) for snapshot in snapshots]

    def _fetch_series(
        self,
        selections: list[Selection],
        selected_at: datetime,
        end_date: datetime,
    ) -> dict:
        series_by_code = {}
        for selection in selections:
            if hasattr(self.market_provider, "reference_date"):
                self.market_provider.reference_date = end_date
            fetched = load_daily_prices(
                self.market_provider,
                self._to_stock(selection),
                selected_at - timedelta(days=365),
                end_date,
            )
            cached = (
                self.candle_repository.load(selection.code)
                if self.candle_repository is not None
                else None
            )
            series = CandleRepository.merge(cached, fetched)
            series_by_code[selection.code] = series
            if self.candle_repository is not None:
                self.candle_repository.save(series)
        return series_by_code

    def _evaluate(
        self,
        selections: list[Selection],
        series_by_code: dict,
        selected_at: datetime,
        evaluation_date: datetime,
        holding_days: int,
        success_return: float,
        trade_time: str | None,
        sell_time: str | None,
        market_trend_filter: bool,
        benchmark_returns: dict[str, float] | None,
    ) -> DeferredValidationResult:
        if benchmark_returns is None and self.benchmark_provider is not None:
            benchmark_returns = self.benchmark_provider.get_returns(
                {
                    selection.analysis.market
                    for selection in selections
                    if selection.analysis.market
                    in (MarketType.KOSPI, MarketType.KOSDAQ)
                },
                selected_at,
                evaluation_date,
            )
        prices = self.price_resolver.resolve(
            selections,
            series_by_code,
            evaluation_date,
            trade_time=trade_time,
            sell_time=sell_time,
        )
        backtest = self.backtest_engine.run(
            selections=selections,
            evaluation_date=evaluation_date,
            holding_days=holding_days,
            selection_prices=prices.selection_prices,
            evaluation_prices=prices.evaluation_prices,
            market_context=market_trend_filter,
            benchmark_returns=benchmark_returns,
        )
        validation = self.validator.validate(backtest, success_return)
        if self.validation_repository is not None:
            self.validation_repository.save(ValidationRecord(
                selected_at=selected_at,
                evaluation_date=evaluation_date,
                holding_days=holding_days,
                success_return=success_return,
                result=validation,
            ))

        return DeferredValidationResult(
            selections=selections,
            backtest=backtest,
            validation=validation,
            report_markdown=self.report_generator.generate_markdown(
                validation,
                selection_results=backtest.results,
                success_return=success_return,
            ),
        )

    @staticmethod
    def _to_selection(snapshot: SelectionSnapshot) -> Selection:
        features = FeatureSet()
        for feature_name in snapshot.enabled_features:
            features.add(Feature.create_enabled(FeatureType(feature_name), 1.0, 1.0))

        prediction = None
        if snapshot.prediction_grade is not None:
            grade = PredictionGrade(snapshot.prediction_grade)
            prediction = PredictionResult(
                total_score=snapshot.normalized_score,
                confidence=0.0,
                expected_return=0.0,
                grade=grade,
            )

        decision = None
        if snapshot.decision is not None:
            decision = DecisionResult(
                decision=DecisionType(snapshot.decision),
                prediction_grade=(
                    prediction.grade if prediction is not None else PredictionGrade.PASS
                ),
                reason="Restored from selection snapshot",
            )

        analysis = AnalysisResult(
            code=snapshot.code,
            name=snapshot.name,
            indicators=None,
            features=features,
            score=ScoreResult(
                trend_score=snapshot.trend_score,
                momentum_score=snapshot.momentum_score,
                volume_score=snapshot.volume_score,
                price_action_score=snapshot.price_action_score,
                risk_score=snapshot.risk_score,
                context_score=snapshot.context_score,
            ),
            prediction=prediction,
            decision=decision,
            positive_factors=snapshot.positive_factors,
            negative_factors=snapshot.negative_factors,
            market=MarketType(snapshot.market) if snapshot.market else None,
            context=DeferredValidationRunner._to_market_context(snapshot.market_context),
        )
        return Selection(analysis, snapshot.selected_at, snapshot.rank)

    @staticmethod
    def _to_market_context(
        payload: dict[str, str | float | int] | None,
    ) -> MarketContext | None:
        if payload is None:
            return None
        return MarketContext(
            kospi_trend=MarketTrend(str(payload["kospi_trend"])),
            kosdaq_trend=MarketTrend(str(payload["kosdaq_trend"])),
            market_strength=float(payload["market_strength"]),
            sector_strength=float(payload["sector_strength"]),
            theme_strength=float(payload["theme_strength"]),
            foreign_flow=float(payload["foreign_flow"]),
            institution_flow=float(payload["institution_flow"]),
            score=int(payload["score"]),
        )

    @staticmethod
    def _to_stock(selection: Selection) -> Stock:
        market = selection.analysis.market
        if market is None:
            raise ValueError(
                f"selection snapshot for {selection.code} has no market value"
            )
        return Stock(selection.code, selection.name, market)
