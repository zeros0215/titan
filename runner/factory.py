from analysis.analyzer import Analyzer
from backtest.engine.backtest_engine import BacktestEngine
from backtest.engine.selection_engine import SelectionEngine
from broker.factory import ProviderFactory
from feature.feature_engine import FeatureEngine
from indicators.calculator import IndicatorCalculator
from market.context.context_builder import MarketContextBuilder
from ranking.ranking_engine import RankingEngine
from report.report_generator import ReportGenerator
from repository.stock_repository import StockRepository
from repository.selection_repository import SelectionRepository
from repository.candle_repository import CandleRepository
from repository.validation_repository import ValidationRepository
from runner.titan_runner import TitanRunner
from runner.deferred_validation_runner import DeferredValidationRunner
from scanner.scanner import Scanner
from scoring.score_engine import ScoreEngine
from prediction.prediction_engine import PredictionEngine
from decision.decision_engine import DecisionEngine
from filter.engine import FilterEngine
from validation.validator import Validator
from config.transaction_costs import transaction_cost_policy_from_env
from benchmark.kis import KisBenchmarkProvider
from benchmark.mock import MockBenchmarkProvider
from broker.kis.market import KisMarketProvider
from repository.observation_repository import ObservationRepository
from config.observation_policy import ObservationPolicy
from config.constants import OUTPUT_DIR
from data.quality import CandleSeriesValidator
from repository.data_quality_repository import DataQualityRepository
from repository.universe_repository import UniverseRepository
from pathlib import Path
from walkforward.engine import WalkForwardEngine
from config.selection_criteria import SELECTION_CRITERIA
from config.constants import VERSION
from data.quarantine import QualityQuarantinePolicy
from broker.historical import HistoricalFileMarketProvider
from release.backtest_data import load_active_backtest_data
from repository.market_cap_stock_repository import MarketCapStockRepository


def create_titan_runner(
    artifact_root: Path | None = None,
    strategy_version: str = VERSION,
    criteria=SELECTION_CRITERIA,
    market_provider=None,
    stock_repository=None,
    quality_quarantine_policy=None,
) -> TitanRunner:
    """Build the V1 runner with the configured market-data provider."""
    market_provider = market_provider or ProviderFactory.create()
    provider_name = (
        "KIS"
        if isinstance(market_provider, KisMarketProvider)
        else (
            "KRX_HISTORICAL"
            if isinstance(market_provider, HistoricalFileMarketProvider)
            else "MOCK"
        )
    )
    analyzer = Analyzer(
        indicator_calculator=IndicatorCalculator(),
        feature_engine=FeatureEngine(),
        score_engine=ScoreEngine(),
        prediction_engine=PredictionEngine(criteria),
        decision_engine=DecisionEngine(),
    )

    return TitanRunner(
        stock_repository=stock_repository or StockRepository(),
        scanner=Scanner(
            market_provider,
            analyzer,
            context_builder=MarketContextBuilder(),
            quality_validator=CandleSeriesValidator(minimum_candles=61),
        ),
        ranking_engine=RankingEngine(),
        selection_engine=SelectionEngine(),
        backtest_engine=BacktestEngine(
            transaction_cost_policy=transaction_cost_policy_from_env()
        ),
        validator=Validator(),
        report_generator=ReportGenerator(),
        selection_repository=SelectionRepository(
            artifact_root / "selections" if artifact_root else None,
            strategy_version=strategy_version,
            provider_name=provider_name,
        ),
        filter_engine=FilterEngine(criteria),
        candle_repository=CandleRepository(
            artifact_root / "market_data" if artifact_root else None
        ),
        benchmark_provider=_benchmark_provider(market_provider),
        observation_repository=ObservationRepository(
            artifact_root / "observations" if artifact_root else None,
            strategy_version=strategy_version,
            provider_name=provider_name,
        ),
        observation_policy=ObservationPolicy(),
        quality_repository=DataQualityRepository(
            artifact_root / "quality" if artifact_root else None
        ),
        universe_repository=UniverseRepository(
            artifact_root / "universe" if artifact_root else None
        ),
        quality_quarantine_policy=quality_quarantine_policy,
    )


def create_deferred_validation_runner(
    artifact_root: Path | None = None,
) -> DeferredValidationRunner:
    """Build the runner that validates previously saved selections."""
    market_provider = ProviderFactory.create()
    return DeferredValidationRunner(
        selection_repository=SelectionRepository(
            artifact_root / "selections" if artifact_root else None
        ),
        market_provider=market_provider,
        backtest_engine=BacktestEngine(
            transaction_cost_policy=transaction_cost_policy_from_env()
        ),
        validator=Validator(),
        report_generator=ReportGenerator(),
        candle_repository=CandleRepository(
            artifact_root / "market_data" if artifact_root else None
        ),
        validation_repository=ValidationRepository(
            artifact_root / "validations" if artifact_root else None
        ),
        benchmark_provider=_benchmark_provider(market_provider),
    )


def create_observation_validation_runner() -> DeferredValidationRunner:
    """Validate the bounded shadow cohort without mixing recommendation history."""
    market_provider = ProviderFactory.create()
    return DeferredValidationRunner(
        selection_repository=ObservationRepository(),
        market_provider=market_provider,
        backtest_engine=BacktestEngine(
            transaction_cost_policy=transaction_cost_policy_from_env()
        ),
        validator=Validator(),
        report_generator=ReportGenerator(),
        candle_repository=CandleRepository(),
        validation_repository=ValidationRepository(
            directory=OUTPUT_DIR / "observation_validations"
        ),
        benchmark_provider=_benchmark_provider(market_provider),
    )


def create_walk_forward_engine(
    strategy_version: str = VERSION,
    criteria=SELECTION_CRITERIA,
    strategy_config_hash: str | None = None,
) -> WalkForwardEngine:
    active_data_path = OUTPUT_DIR / "release" / "backtest_data.json"
    universe_dir, price_dir, _ = load_active_backtest_data(active_data_path)
    artifact_root = OUTPUT_DIR / "walk_forward" / "artifacts" / strategy_version
    return WalkForwardEngine(
        create_titan_runner(
            artifact_root=artifact_root,
            strategy_version=strategy_version,
            criteria=criteria,
            market_provider=HistoricalFileMarketProvider(price_dir),
            stock_repository=MarketCapStockRepository(
                StockRepository(universe_dir),
                price_dir / "market_cap_top500.json",
            ),
            quality_quarantine_policy=QualityQuarantinePolicy.from_file(
                price_dir / "quality_quarantines.json"
            ),
        ),
        _create_historical_validation_runner(artifact_root, price_dir),
        strategy_version=strategy_version,
        strategy_config_hash=strategy_config_hash,
    )


def _create_historical_validation_runner(
    artifact_root: Path,
    price_dir: Path,
) -> DeferredValidationRunner:
    provider = HistoricalFileMarketProvider(price_dir)
    return DeferredValidationRunner(
        selection_repository=SelectionRepository(
            artifact_root / "selections"
        ),
        market_provider=provider,
        backtest_engine=BacktestEngine(
            transaction_cost_policy=transaction_cost_policy_from_env()
        ),
        validator=Validator(),
        report_generator=ReportGenerator(),
        candle_repository=CandleRepository(artifact_root / "market_data"),
        validation_repository=ValidationRepository(
            artifact_root / "validations"
        ),
        # Compiled equity histories do not contain official KOSPI/KOSDAQ
        # index candles. Never mix deterministic MOCK returns into a real
        # KRX baseline; excess return remains unavailable until index data is
        # promoted separately.
        benchmark_provider=None,
    )


def _benchmark_provider(market_provider):
    if isinstance(market_provider, KisMarketProvider):
        return KisBenchmarkProvider(session=market_provider.session)
    return MockBenchmarkProvider()
