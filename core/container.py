"""Compatibility container for the V1 TITAN composition root."""

from runner.factory import (
    create_deferred_validation_runner,
    create_observation_validation_runner,
    create_titan_runner,
    create_walk_forward_engine,
)
from repository.validation_repository import ValidationRepository
from repository.report_repository import ReportRepository
from validation.aggregator import ValidationAggregator
from report.report_generator import ReportGenerator
from repository.walk_forward_repository import WalkForwardRepository
from repository.observation_repository import ObservationRepository
from repository.run_repository import RunRepository
from operation.calendar import CachedMarketCalendar, WeekdayMarketCalendar
from operation.holiday import HolidayCache, KisHolidayProvider
from operation.runner import DailyOperationRunner
from config.constants import OUTPUT_DIR
from broker.kis.market import KisMarketProvider
from monitoring.engine import MonitoringEngine
from repository.monitoring_repository import MonitoringRepository
from repository.data_quality_repository import DataQualityRepository
from repository.strategy_candidate_repository import StrategyCandidateRepository
from strategy_gate.gate import StrategyGate
from strategy_gate.service import StrategyGateService


class Container:
    """Exposes the V1 runner while older callers migrate to ``runner``."""

    def __init__(self) -> None:
        self.runner = create_titan_runner()
        self.deferred_validation_runner = create_deferred_validation_runner()
        self.observation_validation_runner = create_observation_validation_runner()
        self.validation_repository = ValidationRepository()
        self.report_repository = ReportRepository()
        self.validation_aggregator = ValidationAggregator()
        self.report_generator = ReportGenerator()
        self.walk_forward_engine = create_walk_forward_engine()
        self.walk_forward_repository = WalkForwardRepository()
        self.observation_repository = ObservationRepository()
        self.observation_validation_repository = ValidationRepository(
            OUTPUT_DIR / "observation_validations"
        )
        self.run_repository = RunRepository()
        self.monitoring_engine = MonitoringEngine(self.validation_aggregator)
        self.monitoring_repository = MonitoringRepository()
        self.data_quality_repository = DataQualityRepository()
        self.strategy_candidate_repository = StrategyCandidateRepository()
        self.strategy_gate_service = StrategyGateService(
            self.strategy_candidate_repository,
            StrategyGate(),
        )
        market_provider = self.runner.scanner.market_provider
        operation_calendar = (
            CachedMarketCalendar(
                KisHolidayProvider(market_provider.session),
                HolidayCache(),
            )
            if isinstance(market_provider, KisMarketProvider)
            else WeekdayMarketCalendar()
        )
        self.daily_operation_runner = DailyOperationRunner(
            titan_runner=self.runner,
            selected_validation_runner=self.deferred_validation_runner,
            observation_validation_runner=self.observation_validation_runner,
            selection_repository=self.runner.selection_repository,
            observation_repository=self.observation_repository,
            selected_validation_repository=self.validation_repository,
            observation_validation_repository=self.observation_validation_repository,
            run_repository=self.run_repository,
            report_repository=self.report_repository,
            calendar=operation_calendar,
        )
