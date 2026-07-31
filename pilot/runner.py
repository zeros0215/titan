import json
from dataclasses import asdict, replace
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from broker.kis.market import KisMarketProvider
from broker.historical import HistoricalFileMarketProvider
from data.quarantine import QualityQuarantinePolicy
from pilot.model import KisPilotResult
from pilot.report import generate_kis_pilot_markdown
from repository.report_repository import ReportRepository
from repository.stock_repository import StockRepository
from runner.factory import create_titan_runner
from release.backtest_data import load_active_backtest_data
from repository.market_cap_stock_repository import MarketCapStockRepository
from config.settings import settings
from broker.kis.client import KisReadOnlyClient
from broker.kis.session import KisSession
from config.strategy_profiles import get_strategy_profile


class KisPilotRunner:
    def __init__(
        self,
        universe_dir: Path,
        artifact_root: Path,
        active_data_path: Path | None = None,
        strategy_version: str = "V1.1",
        prefer_local_history: bool = False,
    ) -> None:
        self.universe_dir = universe_dir
        self.artifact_root = artifact_root
        self.active_data_path = active_data_path
        self.strategy_version = strategy_version
        self.prefer_local_history = prefer_local_history

    def run(self, as_of: datetime, top_n: int = 5) -> KisPilotResult:
        run_id = f"{as_of:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}"
        run_artifact_root = self.artifact_root / "artifacts" / run_id
        price_dir = None
        if self.active_data_path is not None:
            universe_dir, price_dir, _ = load_active_backtest_data(
                self.active_data_path
            )
            stock_repository = MarketCapStockRepository(
                StockRepository(universe_dir),
                price_dir / "market_cap_top500.json",
            )
        else:
            stock_repository = StockRepository(self.universe_dir)
        use_local_history = (
            self.prefer_local_history
            and price_dir is not None
            and _history_covers(price_dir, as_of.date())
        )
        if use_local_history:
            provider = HistoricalFileMarketProvider(price_dir)
            client = None
            quality_quarantine_policy = QualityQuarantinePolicy.from_file(
                price_dir / "quality_quarantines.json"
            )
            source = "LOCAL_KRX"
        else:
            provider = KisMarketProvider(
                session=KisSession(client=KisReadOnlyClient())
            )
            provider.session.client.minimum_interval_seconds = (
                1.0 if settings.kis_mode.upper() == "VIRTUAL" else 0.06
            )
            client = provider.session.client
            quality_quarantine_policy = None
            source = "KIS"
        profile = get_strategy_profile(self.strategy_version)
        runner = create_titan_runner(
            artifact_root=run_artifact_root,
            market_provider=provider,
            stock_repository=stock_repository,
            strategy_version=profile.version,
            criteria=profile.criteria,
            quality_quarantine_policy=quality_quarantine_policy,
        )
        started = perf_counter()
        try:
            selection = runner.select(as_of, top_n=top_n)
        finally:
            if isinstance(provider, KisMarketProvider):
                provider.session.close()
        duration = perf_counter() - started
        quality = selection.quality_summary
        universe_count = quality.total_count if quality else 0
        excluded = quality.excluded_count if quality else universe_count
        exclusion_rate = excluded / universe_count if universe_count else 1.0
        requests = client.request_count if client is not None else 0
        logical_requests = (
            client.success_count + client.failure_count
            if client is not None
            else 0
        )
        success_rate = (
            client.success_count / logical_requests
            if client is not None and logical_requests
            else 1.0
        )
        retry_rate = (
            client.retry_count / requests
            if client is not None and requests
            else 0.0
        )
        reasons = []
        if selection.fetch_failures:
            reasons.append(
                f"종목 조회 실패 {len(selection.fetch_failures)}건"
            )
        if exclusion_rate > 0.05:
            reasons.append(f"품질 제외율 {exclusion_rate:.2%} > 5%")
        if client is not None and success_rate < 0.98:
            reasons.append(f"API 성공률 {success_rate:.2%} < 98%")
        if retry_rate > 0.20:
            reasons.append(f"API 재시도율 {retry_rate:.2%} > 20%")
        if client is not None and client.order_request_count:
            reasons.append(
                f"읽기 전용 위반 {client.order_request_count}건"
            )
        status = (
            "PASS"
            if not reasons
            else "PARTIAL"
            if quality and quality.valid_count
            else "FAIL"
        )
        result = KisPilotResult(
            run_id=run_id,
            as_of=as_of,
            status=status,
            duration_seconds=duration,
            universe_count=universe_count,
            analyzed_count=quality.valid_count if quality else 0,
            selection_count=len(selection.selections),
            observation_count=len(selection.observations),
            excluded_count=excluded,
            exclusion_rate=exclusion_rate,
            fetch_failures=selection.fetch_failures,
            request_count=requests,
            success_count=client.success_count if client is not None else 0,
            retry_count=client.retry_count if client is not None else 0,
            retry_rate=retry_rate,
            failure_count=client.failure_count if client is not None else 0,
            server_error_count=(
                client.server_error_count if client is not None else 0
            ),
            transport_error_count=(
                client.transport_error_count if client is not None else 0
            ),
            api_success_rate=success_rate,
            order_request_count=(
                client.order_request_count if client is not None else 0
            ),
            selected_candidates=self._candidate_rows(selection.selections),
            observation_candidates=self._candidate_rows(
                selection.observations
            ),
            snapshot_path=selection.snapshot_path,
            reasons=reasons,
            strategy_version=profile.version,
            source=source,
        )
        report_repository = ReportRepository(self.artifact_root / "reports")
        report_path = report_repository.save(
            f"pilot_{run_id}.md",
            generate_kis_pilot_markdown(result),
        )
        result = replace(result, report_path=report_path)
        self._save_result(result)
        return result

    def _save_result(self, result):
        directory = self.artifact_root / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        payload = asdict(result)
        for key, value in list(payload.items()):
            if isinstance(value, Path):
                payload[key] = str(value)
            elif isinstance(value, datetime):
                payload[key] = value.isoformat()
            elif isinstance(value, Enum):
                payload[key] = value.value
        (directory / f"{result.run_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _candidate_rows(candidates):
        rows = []
        for candidate in candidates:
            analysis = candidate.analysis
            score = analysis.score
            context = analysis.context
            trend = ""
            if context is not None and analysis.market is not None:
                trend = (
                    context.kospi_trend.value
                    if analysis.market.value == "KOSPI"
                    else context.kosdaq_trend.value
                )
            rows.append({
                "rank": candidate.rank,
                "code": candidate.code,
                "name": candidate.name,
                "total_score": score.normalized_score,
                "trend_score": score.trend_score,
                "momentum_score": score.momentum_score,
                "volume_score": score.volume_score,
                "price_action_score": score.price_action_score,
                "risk_score": score.risk_score,
                "context_score": score.context_score,
                "market_trend": trend,
                "market_strength": (
                    context.market_strength if context is not None else None
                ),
                "positive_factors": list(analysis.positive_factors),
                "negative_factors": list(analysis.negative_factors),
            })
        return rows


def _history_covers(price_dir: Path, target: date) -> bool:
    manifest_path = price_dir / "price_history_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        coverage_start = date.fromisoformat(manifest["coverage_start"])
        coverage_end = date.fromisoformat(manifest["coverage_end"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return coverage_start <= target <= coverage_end
