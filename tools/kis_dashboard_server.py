"""Local-only web server for dated KIS read-only pilot tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
import gzip
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

import httpx

from analysis.event_candidates import (
    evaluate_event_quote,
    session_progress,
    snapshot_phase,
)
from broker.kis.current_price import KisCurrentPriceProvider
from broker.kis.exception import KisApiException
from price_history.krx import (
    KrxPriceClient,
    KrxPriceCollector,
    KrxPriceRawRepository,
)
from pilot.history import PilotHistoryRepository
from tools.build_kis_dashboard import LOCAL_INDEX, ROOT, main as build_dashboard
from tools.local_monthly_test import run_date, run_month, run_year
from release.backtest_data import load_active_backtest_data
from repository.stock_repository import StockRepository
from analysis.industry_relative_strength import run_industry_rs_validation
from analysis.pre_breakout_scanner import (
    run_pre_breakout_monthly_validation,
    run_pre_breakout_scan,
)
from universe_history.krx import (
    KrxRawRepository,
    KrxUniverseClient,
    KrxUniverseCollector,
)
from research.strategy_search import (
    generate_bounded_candidates,
    rank_walk_forward_results,
    render_ranking_markdown,
    save_candidate_grid,
)


HOST = "127.0.0.1"
PORT = 8765
RUN_LOCK = threading.Lock()
PRICE_LOCK = threading.Lock()
OPERATIONAL_VERSION = "V1.3-S80-N7-TP5-SL10-CANDIDATE"
ACTIVE_TASK: dict[str, str] = {}


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(200, {
                "busy": RUN_LOCK.locked(),
                "task": ACTIVE_TASK.get("task"),
                "started_at": ACTIVE_TASK.get("started_at"),
            })
            return
        if path not in ("/", "/index.html"):
            self.send_error(404)
            return
        if not LOCAL_INDEX.exists():
            build_dashboard()
        content = LOCAL_INDEX.read_bytes()
        accepts_gzip = "gzip" in self.headers.get("Accept-Encoding", "")
        if accepts_gzip:
            content = gzip.compress(content, compresslevel=1)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if accepts_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in (
            "/api/run",
            "/api/run-month",
            "/api/run-year",
            "/api/run-industry-rs",
            "/api/run-data-update",
            "/api/run-operational-selection",
            "/api/run-pre-breakout",
            "/api/run-pre-breakout-month",
            "/api/current-prices",
            "/api/news-headlines",
            "/api/run-event-candidates",
            "/api/research-generate",
            "/api/research-rank",
            "/api/research-run",
            "/api/research-run-weekly",
            "/api/research-run-challengers",
            "/api/research-shadow-run",
            "/api/research-shadow-replay",
            "/api/research-shadow-weekday",
        ):
            self._json(
                404,
                {
                    "message": (
                        f"지원하지 않는 API 경로입니다: {path}. "
                        "대시보드 서버를 재시작해 주세요."
                    )
                },
            )
            return
        if path == "/api/run-industry-rs":
            self._run_industry_rs()
            return
        if path == "/api/current-prices":
            self._current_prices()
            return
        if path == "/api/news-headlines":
            self._news_headlines()
            return
        if path == "/api/run-event-candidates":
            self._run_event_candidates()
            return
        if path == "/api/research-generate":
            candidates = generate_bounded_candidates()
            manifest = save_candidate_grid(
                ROOT / "output" / "strategy_research" / "candidates",
                candidates,
            )
            build_dashboard()
            self._json(200, {
                "message": "연구 후보 생성 완료",
                "candidate_count": len(candidates),
                "manifest": str(manifest.relative_to(ROOT)),
                "operational_strategy_unchanged": True,
            })
            return
        if path == "/api/research-shadow-run":
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "another task is already running"})
                return
            _set_active_task("STRATEGY_SHADOW")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "app.main", "strategy-shadow-run"],
                    cwd=ROOT, capture_output=True, text=True, timeout=1800,
                )
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {"message": output.splitlines()[-1] if output else "shadow run failed"})
                    return
                build_dashboard()
                self._json(200, {
                    "message": "A/C shadow run completed",
                    "operational_orders": 0,
                })
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "shadow run exceeded 30 minutes"})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/research-shadow-replay":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                month = datetime.strptime(payload["month"], "%Y-%m").strftime("%Y-%m")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self._json(400, {"message": "month must use YYYY-MM format"})
                return
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "another task is already running"})
                return
            _set_active_task("STRATEGY_SHADOW_REPLAY")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "app.main", "strategy-shadow-replay", "--month", month],
                    cwd=ROOT, capture_output=True, text=True, timeout=3600,
                )
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {"message": output.splitlines()[-1] if output else "shadow replay failed"})
                    return
                build_dashboard()
                self._json(200, {
                    "message": f"{month} weekly shadow replay completed",
                    "operational_orders": 0,
                })
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "shadow replay exceeded 60 minutes"})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/research-shadow-weekday":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                start = datetime.strptime(payload["start_month"], "%Y-%m").strftime("%Y-%m")
                end = datetime.strptime(payload["end_month"], "%Y-%m").strftime("%Y-%m")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self._json(400, {"message": "months must use YYYY-MM format"})
                return
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "another task is already running"})
                return
            _set_active_task("STRATEGY_WEEKDAY_TEST")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "app.main", "strategy-shadow-weekday-test", "--start-month", start, "--end-month", end],
                    cwd=ROOT, capture_output=True, text=True, timeout=3600,
                )
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {"message": output.splitlines()[-1] if output else "weekday test failed"})
                    return
                build_dashboard()
                self._json(200, {"message": f"{start}..{end} weekday test completed", "operational_orders": 0})
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "weekday test exceeded 60 minutes"})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/research-rank":
            paths = sorted((ROOT / "output" / "walk_forward").glob("walk_forward_result_*.json"))
            rows = rank_walk_forward_results(paths, minimum_trades=100)
            output = ROOT / "output" / "strategy_research" / "ranking.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(render_ranking_markdown(rows), encoding="utf-8")
            build_dashboard()
            self._json(200, {
                "message": "기존 워크포워드 결과 순위 계산 완료",
                "result_count": len(rows),
                "eligible_count": sum(row["eligible"] for row in rows),
                "operational_strategy_unchanged": True,
            })
            return
        if path == "/api/research-monthly-rs":
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "another task is already running"})
                return
            _set_active_task("STRATEGY_MONTHLY_RS")
            try:
                data_path = ROOT / "output" / "data_extensions" / "2020_20260805" / "backtest_data.json"
                result = subprocess.run(
                    [sys.executable, "-m", "app.main", "strategy-monthly-rs-test",
                     "--active-data", str(data_path), "--start-year", "2021",
                     "--end-date", "2026-08-05", "--defensive"],
                    cwd=ROOT, capture_output=True, text=True, timeout=600,
                )
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {"message": output.splitlines()[-1] if output else "monthly RS test failed"})
                    return
                build_dashboard()
                self._json(200, {"message": "I 월간 전략 검증 완료", "operational_orders": 0})
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "monthly RS test exceeded 10 minutes"})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/research-run":
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "다른 작업이 이미 실행 중입니다."})
                return
            _set_active_task("STRATEGY_RESEARCH")
            try:
                result = subprocess.run(
                    [
                        sys.executable, "-m", "app.main",
                        "strategy-research-run",
                        "--history-start-year", "2022",
                        "--first-test-year", "2023",
                        "--last-test-year", "2025",
                    ],
                    cwd=ROOT, capture_output=True, text=True, timeout=3600,
                )
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {"message": output.splitlines()[-1] if output else "연구 실행 실패"})
                    return
                paths = sorted((ROOT / "output" / "walk_forward").glob("walk_forward_result_*.json"))
                rows = rank_walk_forward_results(paths, minimum_trades=100)
                ranking = ROOT / "output" / "strategy_research" / "ranking.md"
                ranking.write_text(render_ranking_markdown(rows), encoding="utf-8")
                build_dashboard()
                self._json(200, {
                    "message": "대표 후보 5개 워크포워드 완료",
                    "result_count": len(rows),
                    "operational_strategy_unchanged": True,
                })
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "전략 연구가 60분 제한을 초과했습니다."})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/research-run-challengers":
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "another task is already running"})
                return
            _set_active_task("STRATEGY_CHALLENGERS")
            try:
                result = subprocess.run(
                    [
                        sys.executable, "-m", "app.main",
                        "strategy-research-run",
                        "--history-start-year", "2022",
                        "--first-test-year", "2023",
                        "--last-test-year", "2026",
                        "--challenger-experiment",
                    ],
                    cwd=ROOT, capture_output=True, text=True, timeout=7200,
                )
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {
                        "message": output.splitlines()[-1]
                        if output else "challenger research failed",
                    })
                    return
                paths = sorted(
                    (ROOT / "output" / "walk_forward").glob("walk_forward_result_*.json")
                )
                rows = rank_walk_forward_results(paths, minimum_trades=100)
                ranking = ROOT / "output" / "strategy_research" / "ranking.md"
                ranking.write_text(
                    render_ranking_markdown(rows), encoding="utf-8"
                )
                build_dashboard()
                self._json(200, {
                    "message": "six challenger validations completed",
                    "result_count": len(rows),
                    "operational_strategy_unchanged": True,
                })
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "challenger research exceeded 120 minutes"})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/research-run-weekly":
            if not RUN_LOCK.acquire(blocking=False):
                self._json(409, {"message": "다른 작업이 이미 실행 중입니다."})
                return
            _set_active_task("STRATEGY_RESEARCH_WEEKLY")
            try:
                result = subprocess.run([
                    sys.executable, "-m", "app.main", "strategy-research-run",
                    "--history-start-year", "2022", "--first-test-year", "2023",
                    "--last-test-year", "2025", "--weekly",
                ], cwd=ROOT, capture_output=True, text=True, timeout=3600)
                if result.returncode:
                    output = "\n".join((result.stdout, result.stderr)).strip()
                    self._json(500, {"message": output.splitlines()[-1] if output else "주간 연구 실패"})
                    return
                rows = rank_walk_forward_results(
                    sorted((ROOT / "output" / "walk_forward").glob("walk_forward_result_*.json")), 100,
                )
                ranking = ROOT / "output" / "strategy_research" / "ranking.md"
                ranking.write_text(render_ranking_markdown(rows), encoding="utf-8")
                build_dashboard()
                self._json(200, {"message": "기준형·위험강화형 주간 검증 완료"})
            except subprocess.TimeoutExpired:
                self._json(504, {"message": "주간 연구가 60분 제한을 초과했습니다."})
            finally:
                _clear_active_task()
                RUN_LOCK.release()
            return
        if path == "/api/run-data-update":
            self._run_data_update()
            return
        if path == "/api/run-operational-selection":
            self._run_operational_selection()
            return
        if path == "/api/run-pre-breakout":
            self._run_pre_breakout()
            return
        if path == "/api/run-pre-breakout-month":
            self._run_pre_breakout_month()
            return
        if path == "/api/run-month":
            self._run_month()
            return
        if path == "/api/run-year":
            self._run_year()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            as_of = date.fromisoformat(payload["date"])
            if as_of > date.today():
                raise ValueError("미래 날짜는 실행할 수 없습니다.")
            now = datetime.now()
            if (
                as_of == now.date()
                and now.time() < datetime.strptime("15:40", "%H:%M").time()
            ):
                raise ValueError(
                    "당일 KIS 테스트는 일봉이 확정되는 15:40 이후에 "
                    "실행하세요. 지금은 직전 거래일을 선택할 수 있습니다."
                )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"message": str(exc) or "날짜 형식이 올바르지 않습니다."})
            return

        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        _set_active_task("DAILY_TEST")
        try:
            if as_of < date.today():
                local_result = run_date(as_of.isoformat(), top_n=5)
                build_dashboard()
                self._json(200, {
                    "message": "로컬 KRX 데이터로 완료",
                    "source": "LOCAL_KRX",
                    "analyzed_count": local_result["analyzed_count"],
                    "selection_count": local_result["selection_count"],
                    "observation_count": local_result["observation_count"],
                })
                return
            result = subprocess.run(
                [
                    sys.executable, "-m", "app.main", "kis-pilot",
                    "--date", as_of.isoformat(),
                    "--top-n", "5",
                    "--active-data", "output/release/backtest_data.json",
                    "--output-dir", "output/kis_manual_tests",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            build_dashboard()
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            if result.returncode not in (0, 3):
                message = output.strip().splitlines()[-1] if output.strip() else "테스트 실행에 실패했습니다."
                self._json(500, {"message": message})
                return
            self._json(200, {
                "message": "KIS 조회로 완료",
                "source": "KIS",
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            self._json(504, {"message": "테스트가 30분 제한시간을 초과했습니다."})
        finally:
            _clear_active_task()
            RUN_LOCK.release()

    def _run_month(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            month = datetime.strptime(payload["month"], "%Y-%m").strftime(
                "%Y-%m"
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "월은 YYYY-MM 형식이어야 합니다."})
            return
        try:
            holding_sessions = int(payload.get("holding_sessions", 1))
        except (TypeError, ValueError):
            self._json(400, {"message": "매도 기간이 올바르지 않습니다."})
            return
        if holding_sessions not in (1, 5, 10, 20):
            self._json(400, {"message": "매도 기간은 1·5·10·20일 중 하나여야 합니다."})
            return
        try:
            profit_target, stop_loss = _parse_exit_rates(payload)
            entry_mode, entry_limit, entry_minimum = _parse_entry_settings(payload)
        except (TypeError, ValueError) as exc:
            self._json(400, {"message": str(exc)})
            return
        strategy_version = payload.get("strategy_version", "V1.1")
        if strategy_version not in (
                "V1.1",
                "V1.2-CANDIDATE",
                "V1.2-GAP-CANDIDATE",
                "V1.2-5D-CANDIDATE",
                "V1.3-RISK-5D-CANDIDATE",
                "V1.3-S78-N7-CANDIDATE",
                "V1.3-S78-N7-TP5-SL10-CANDIDATE",
                "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                "V1.3-S79-N2-TP5-SL10-CANDIDATE",
                "V1.3-DUAL-5D-S80-N7-TP5-SL10-CANDIDATE",
        ):
            self._json(400, {"message": f"지원하지 않는 전략입니다: {strategy_version}"})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
            results = run_month(
                month,
                holding_sessions=holding_sessions,
                strategy_version=strategy_version,
                profit_target=profit_target,
                stop_loss=stop_loss,
                entry_mode=entry_mode,
                entry_limit=entry_limit,
                entry_minimum=entry_minimum,
            )
            build_dashboard()
            self._json(
                200,
                {"message": "완료", "trading_days": len(results)},
            )
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"월간 테스트 실패: {exc}"})
        finally:
            RUN_LOCK.release()

    def _run_operational_selection(self) -> None:
        now = datetime.now()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            selection_date = _parse_operational_selection_date(
                payload.get("date"),
                now,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"message": str(exc)})
            return
        cached = _find_cached_operational_selection(
            ROOT / "output" / "kis_v1_1" / "runs",
            selection_date,
        )
        if cached is not None:
            self._json(
                200,
                {
                    "message": (
                        "동일 기준일의 정상 완료 결과를 저장 데이터에서 "
                        "불러왔습니다."
                    ),
                    "date": selection_date.isoformat(),
                    "cached": True,
                    "source": cached.get("source"),
                    "selection_count": cached.get("selection_count", 0),
                    "observation_count": cached.get(
                        "observation_count",
                        len(cached.get("observation_candidates") or []),
                    ),
                },
            )
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 작업이 이미 실행 중입니다."})
            return
        _set_active_task("S80_OPERATIONAL_SELECTION")
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "app.main", "kis-pilot",
                    "--date", selection_date.isoformat(),
                    "--top-n", "7",
                    "--strategy-version",
                    "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                    "--active-data", "output/release/backtest_data.json",
                    "--output-dir", "output/kis_v1_1",
                    "--prefer-local-history",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            build_dashboard()
            output = "\n".join(
                part for part in (result.stdout, result.stderr) if part
            )
            if result.returncode not in (0, 3):
                message = (
                    output.strip().splitlines()[-1]
                    if output.strip()
                    else "S80 선정 작업에 실패했습니다."
                )
                self._json(500, {"message": message})
                return
            self._json(
                200,
                {
                    "message": "S80 종목 선정이 완료되었습니다.",
                    "date": selection_date.isoformat(),
                    "cached": False,
                    "returncode": result.returncode,
                },
            )
        except subprocess.TimeoutExpired:
            self._json(504, {"message": "선정 작업이 30분 제한을 초과했습니다."})
        finally:
            _clear_active_task()
            RUN_LOCK.release()

    def _current_prices(self) -> None:
        if RUN_LOCK.locked():
            self._json(409, {"message": "종목 선정 작업 중에는 현재가를 갱신하지 않습니다."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            codes = [str(code).zfill(6) for code in payload.get("codes", [])]
            if not codes or len(codes) > 20:
                raise ValueError("현재가는 1~20개 종목을 조회할 수 있습니다.")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"message": str(exc)})
            return
        if not PRICE_LOCK.acquire(blocking=False):
            self._json(409, {"message": "현재가를 이미 갱신 중입니다."})
            return
        provider = KisCurrentPriceProvider()
        try:
            prices = provider.get_prices(codes)
            snapshot = _save_operational_entry_snapshot(prices)
            self._json(200, {
                "prices": prices,
                "entry_snapshot_saved": snapshot is not None,
                "entry_snapshot": snapshot,
            })
        except (
            OSError, TypeError, ValueError, KisApiException, httpx.HTTPError,
        ) as exc:
            self._json(502, {"message": f"KIS 현재가 조회 실패: {exc}"})
        finally:
            provider.close()
            PRICE_LOCK.release()

    def _news_headlines(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            code = str(payload.get("code", "")).strip()
            name = str(payload.get("name", "")).strip()
            if not name or len(name) > 40:
                raise ValueError("종목명이 올바르지 않습니다.")
            if code and (len(code) != 6 or not code.isdigit()):
                raise ValueError("종목코드는 6자리 숫자여야 합니다.")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"message": str(exc)})
            return

        query, rss_url, search_url = _news_urls(name)
        try:
            headlines = _fetch_news_headlines(rss_url, limit=12)
            self._json(
                200,
                {
                    "code": code,
                    "name": name,
                    "query": query,
                    "headlines": headlines,
                    "search_url": search_url,
                    "checked_at": datetime.now().astimezone().isoformat(),
                    "title_only": True,
                },
            )
        except (ElementTree.ParseError, httpx.HTTPError) as exc:
            self._json(
                502,
                {
                    "message": f"기사 제목 검색 실패: {exc}",
                    "search_url": search_url,
                },
            )

    def _run_event_candidates(self) -> None:
        if RUN_LOCK.locked():
            self._json(
                409,
                {"message": "S80 종목 선정이 끝난 후 이벤트 후보를 검색해 주세요."},
            )
            return
        if not PRICE_LOCK.acquire(blocking=False):
            self._json(409, {"message": "현재가 또는 이벤트 후보를 이미 조회 중입니다."})
            return
        provider = KisCurrentPriceProvider()
        try:
            universe_dir, price_dir, _ = load_active_backtest_data(
                ROOT / "output" / "release" / "backtest_data.json"
            )
            ranking = json.loads(
                (price_dir / "market_cap_top500.json").read_text(
                    encoding="utf-8"
                )
            )
            session_key = sorted(ranking["sessions"])[-1]
            ranked_codes = ranking["sessions"][session_key]
            names = {
                stock.code: stock.name
                for stock in StockRepository(universe_dir).get_all()
            }
            eligible: dict[str, dict[str, float]] = {}
            for raw_code in ranked_codes:
                code = str(raw_code).zfill(6)
                if len(code) != 6 or not code.isdigit() or code not in names:
                    continue
                try:
                    candles = json.loads(
                        (price_dir / f"{code}.json").read_text(encoding="utf-8")
                    ).get("candles", [])
                    previous = candles[-1]
                    previous_volume = float(previous["volume"])
                    previous_value = float(previous["close"]) * previous_volume
                    history = candles[-21:-1]
                    average_volume = (
                        sum(float(candle["volume"]) for candle in history)
                        / len(history)
                    )
                    volume_ratio = (
                        previous_volume / average_volume
                        if average_volume else 0.0
                    )
                except (
                    OSError, IndexError, KeyError, TypeError, ValueError,
                    json.JSONDecodeError,
                ):
                    continue
                if previous_value >= 5_000_000_000:
                    eligible[code] = {
                        "previous_volume": previous_volume,
                        "previous_volume_ratio": volume_ratio,
                    }

            market_news = _discover_market_event_headlines(names)
            local_codes = sorted(
                eligible,
                key=lambda code: eligible[code]["previous_volume_ratio"],
                reverse=True,
            )[:30]
            news_codes = sorted(
                (code for code in market_news if code in eligible),
                key=lambda code: len(market_news[code]),
                reverse=True,
            )[:30]
            scan_codes = list(dict.fromkeys(news_codes + local_codes))

            now = datetime.now().astimezone()
            progress = session_progress(now)
            rows = []
            evaluations = []
            failures = {}
            consecutive_failures = 0
            for code in scan_codes:
                previous_volume = eligible[code]["previous_volume"]
                try:
                    quote = provider.get_prices([code])[code]
                    consecutive_failures = 0
                except (
                    OSError, TypeError, ValueError,
                    KisApiException, httpx.HTTPError,
                ) as exc:
                    failures[code] = f"{type(exc).__name__}: {exc}"
                    consecutive_failures += 1
                    if consecutive_failures >= 5 and not rows:
                        raise RuntimeError(
                            "KIS 현재가 조회가 연속 5회 실패했습니다. "
                            "인증과 API 접근 권한을 확인해 주세요."
                        ) from exc
                    continue
                evaluation = evaluate_event_quote(
                    quote,
                    previous_volume=previous_volume,
                    progress=progress,
                )
                evaluations.append({
                    "code": code,
                    "name": names[code],
                    "qualified": evaluation["qualified"],
                    "reason": evaluation["reason"],
                    "reason_detail": evaluation["reason_detail"],
                })
                if evaluation["qualified"]:
                    rows.append(
                        {
                            "code": code,
                            "name": names[code],
                            "prefilter": (
                                "NEWS"
                                if code in market_news
                                else "PREVIOUS_VOLUME"
                            ),
                            "previous_volume_ratio": eligible[code][
                                "previous_volume_ratio"
                            ],
                            **quote,
                            **evaluation,
                        }
                    )

            rows.sort(
                key=lambda item: float(item.get("volume_speed") or 0),
                reverse=True,
            )
            rows = rows[:30]
            with ThreadPoolExecutor(max_workers=6) as executor:
                pending = {
                    executor.submit(
                        _fetch_news_headlines,
                        _news_urls(row["name"])[1],
                        5,
                    ): row
                    for row in rows
                }
                for future in as_completed(pending):
                    row = pending[future]
                    try:
                        exact = future.result()
                    except (ElementTree.ParseError, httpx.HTTPError):
                        exact = []
                    combined = market_news.get(row["code"], []) + exact
                    row["headlines"] = list(
                        {
                            (item["title"], item["url"]): item
                            for item in combined
                        }.values()
                    )[:5]
                    row["headline_count"] = len(row["headlines"])
                    row["decision"] = (
                        "10시 검토"
                        if row["headline_count"]
                        else "수급 관찰"
                    )

            output_dir = ROOT / "output" / "event_candidates" / "runs"
            output_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "executed_at": now.isoformat(timespec="seconds"),
                "source": "KIS_REALTIME+GOOGLE_NEWS_TITLES",
                "shadow_only": True,
                "snapshot_phase": snapshot_phase(now),
                "eligible_count": len(eligible),
                "prefiltered_count": len(scan_codes),
                "quoted_count": len(scan_codes) - len(failures),
                "failure_count": len(failures),
                "criteria": {
                    "change_rate": [-0.01, 0.03],
                    "minimum_volume_speed": 2.0,
                    "require_above_open": True,
                    "require_above_vwap": True,
                },
                "candidates": rows,
                "evaluation_summary": {
                    reason: sum(
                        item["reason"] == reason for item in evaluations
                    )
                    for reason in (
                        "EVENT_REVIEW",
                        "PRICE_OUT_OF_RANGE",
                        "BELOW_OPEN",
                        "BELOW_VWAP",
                        "VOLUME_NOT_ACCELERATING",
                    )
                },
                "evaluations": evaluations,
                "failures": failures,
            }
            target = output_dir / f"{now:%Y%m%dT%H%M%S}.json"
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            build_dashboard()
            self._json(
                200,
                {
                    "message": (
                        f"이벤트 후보 {len(rows)}종목을 찾았습니다. "
                        "실제 주문은 실행하지 않습니다."
                    ),
                    **payload,
                },
            )
        except (
            OSError, KeyError, TypeError, ValueError, RuntimeError,
            json.JSONDecodeError, KisApiException, httpx.HTTPError,
        ) as exc:
            self._json(502, {"message": f"이벤트 후보 검색 실패: {exc}"})
        finally:
            provider.close()
            PRICE_LOCK.release()

    def _run_year(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            year = datetime.strptime(str(payload["year"]), "%Y").strftime(
                "%Y"
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "연도는 YYYY 형식이어야 합니다."})
            return
        try:
            holding_sessions = int(payload.get("holding_sessions", 1))
        except (TypeError, ValueError):
            self._json(400, {"message": "매도 기간이 올바르지 않습니다."})
            return
        if holding_sessions not in (1, 5, 10, 20):
            self._json(400, {"message": "매도 기간은 1·5·10·20일 중 하나여야 합니다."})
            return
        try:
            profit_target, stop_loss = _parse_exit_rates(payload)
            entry_mode, entry_limit, entry_minimum = _parse_entry_settings(payload)
        except (TypeError, ValueError) as exc:
            self._json(400, {"message": str(exc)})
            return
        strategy_version = payload.get("strategy_version", "V1.1")
        if strategy_version not in (
                "V1.1",
                "V1.2-CANDIDATE",
                "V1.2-GAP-CANDIDATE",
                "V1.2-5D-CANDIDATE",
                "V1.3-RISK-5D-CANDIDATE",
                "V1.3-S78-N7-CANDIDATE",
                "V1.3-S78-N7-TP5-SL10-CANDIDATE",
                "V1.3-S80-N7-TP5-SL10-CANDIDATE",
                "V1.3-S79-N2-TP5-SL10-CANDIDATE",
                "V1.3-DUAL-5D-S80-N7-TP5-SL10-CANDIDATE",
        ):
            self._json(400, {"message": f"지원하지 않는 전략입니다: {strategy_version}"})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
            results = run_year(
                year,
                holding_sessions=holding_sessions,
                strategy_version=strategy_version,
                profit_target=profit_target,
                stop_loss=stop_loss,
                entry_mode=entry_mode,
                entry_limit=entry_limit,
                entry_minimum=entry_minimum,
            )
            build_dashboard()
            self._json(
                200,
                {"message": "완료", "trading_days": len(results)},
            )
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"연간 테스트 실패: {exc}"})
        finally:
            RUN_LOCK.release()

    def _run_industry_rs(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            start_date = date.fromisoformat(
                payload.get("start_date", "2022-04-01")
            ).isoformat()
            end_date = date.fromisoformat(
                payload.get("end_date", "2023-09-01")
            ).isoformat()
        except (TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "종료 월은 YYYY-MM 형식이어야 합니다."})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
            result, _ = run_industry_rs_validation(
                ROOT / "output" / "release" / "backtest_data.json",
                ROOT / "output" / "industry_rs",
                start_date=start_date,
                end_date=end_date,
            )
            build_dashboard()
            self._json(
                200,
                {
                    "message": "완료",
                    "observations": result["observation_count"],
                    "validation_dates": result["validation_date_count"],
                },
            )
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"패턴 테스트 실패: {exc}"})
        finally:
            RUN_LOCK.release()

    def _run_data_update(self) -> None:
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 작업이 이미 실행 중입니다."})
            return
        _set_active_task("DATA_UPDATE")
        try:
            target = _latest_completed_weekday()
            active_path = ROOT / "output" / "release" / "backtest_data.json"
            active = json.loads(active_path.read_text(encoding="utf-8"))
            price_manifest = json.loads(
                (
                    Path(active["price_dir"]) / "price_history_manifest.json"
                ).read_text(encoding="utf-8")
            )
            current = date.fromisoformat(price_manifest["coverage_end"])
            if current >= target:
                self._json(200, {
                    "message": "이미 최신 데이터입니다.",
                    "coverage_end": current.isoformat(),
                    "updated_sessions": 0,
                })
                return

            universe_raw = ROOT / "output" / "krx_raw_2022_2025"
            price_raw = ROOT / "output" / "krx_price_raw_2022_2025"
            version = datetime.now().strftime("%Y%m%dT%H%M%S")
            staging_root = ROOT / "output" / "data_updates" / version
            universe_staging = staging_root / "universe"
            price_staging = staging_root / "price"
            auth_key = os.getenv("KRX_AUTH_KEY", "")
            universe_repository = KrxRawRepository(universe_raw)
            universe_result = KrxUniverseCollector(
                KrxUniverseClient(auth_key),
                universe_repository,
            ).collect(date(2022, 1, 1), target)
            universe_repository.save_collection_manifest({
                "schema_version": 1,
                "source_name": "KRX Data Marketplace OPEN API",
                "source_type": "official_daily_snapshots",
                "dataset_id": "stk_isu_base_info+ksq_isu_base_info",
                "evidence_url": (
                    "https://openapi.krx.co.kr/contents/OPP/INFO/"
                    "service/OPPINFO004.cmd"
                ),
                "acquired_at": datetime.now().astimezone().isoformat(),
                "coverage_start": "2022-01-01",
                "coverage_end": target.isoformat(),
                "source_complete": universe_result.completed,
                "requested_dates": universe_result.requested_dates,
                "api_calls": universe_result.api_calls,
                "saved_responses": universe_result.saved_responses,
                "skipped_cached": universe_result.skipped_cached,
                "last_date": (
                    universe_result.last_date.isoformat()
                    if universe_result.last_date else None
                ),
                "raw_sha256": universe_repository.content_sha256(),
            })
            price_repository = KrxPriceRawRepository(price_raw)
            price_result = KrxPriceCollector(
                KrxPriceClient(auth_key),
                price_repository,
            ).collect(date(2022, 1, 1), target)
            price_manifest = {
                "schema_version": 1,
                "source_name": "KRX Data Marketplace OPEN API",
                "dataset_id": "stk_bydd_trd+ksq_bydd_trd",
                "coverage_start": "2022-01-01",
                "coverage_end": target.isoformat(),
                "completed": price_result.completed,
                "api_calls": price_result.api_calls,
                "saved_responses": price_result.saved_responses,
                "skipped_cached": price_result.skipped_cached,
                "raw_sha256": price_repository.content_sha256(),
                "prices_adjusted": False,
            }
            (price_raw / "collection_manifest.json").write_text(
                json.dumps(price_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            commands = [
                [
                    sys.executable, "-m", "app.main", "krx-universe-build",
                    "--raw-dir", str(universe_raw),
                    "--output-dir", str(universe_staging),
                ],
                [
                    sys.executable, "-m", "app.main", "krx-price-build",
                    "--universe-raw-dir", str(universe_raw),
                    "--price-raw-dir", str(price_raw),
                    "--output-dir", str(price_staging),
                ],
                [
                    sys.executable, "-m", "app.main", "backtest-data-promote",
                    "--universe-dir", str(universe_staging),
                    "--price-dir", str(price_staging),
                    "--output", str(active_path),
                ],
            ]
            for command in commands:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                if result.returncode != 0:
                    output = "\n".join(
                        part for part in (result.stdout, result.stderr) if part
                    )
                    message = (
                        output.strip().splitlines()[-1]
                        if output.strip()
                        else "데이터 업데이트 단계가 실패했습니다."
                    )
                    raise RuntimeError(message)
            build_dashboard()
            self._json(200, {
                "message": "데이터 업데이트 및 활성화가 완료되었습니다.",
                "coverage_end": target.isoformat(),
                "updated_sessions": _weekdays_between(current, target),
            })
        except subprocess.TimeoutExpired:
            self._json(504, {"message": "데이터 업데이트가 30분을 초과했습니다."})
        except (
            OSError, KeyError, TypeError, ValueError,
            json.JSONDecodeError, RuntimeError, httpx.HTTPError,
        ) as exc:
            self._json(500, {"message": f"데이터 업데이트 실패: {exc}"})
        finally:
            _clear_active_task()
            RUN_LOCK.release()

    def _run_pre_breakout(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            as_of = date.fromisoformat(payload["date"]).isoformat()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "날짜는 YYYY-MM-DD 형식이어야 합니다."})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 작업이 이미 실행 중입니다."})
            return
        try:
            result, _ = run_pre_breakout_scan(
                ROOT / "output" / "release" / "backtest_data.json",
                ROOT / "output" / "pre_breakout",
                as_of,
            )
            build_dashboard()
            self._json(200, {
                "message": "급등 전 후보 검색 완료",
                "qualified_count": result["qualified_count"],
                "analyzed_count": result["analyzed_count"],
            })
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"급등 전 후보 검색 실패: {exc}"})
        finally:
            RUN_LOCK.release()

    def _run_pre_breakout_month(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            month = datetime.strptime(payload["month"], "%Y-%m").strftime("%Y-%m")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "월은 YYYY-MM 형식이어야 합니다."})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 작업이 이미 실행 중입니다."})
            return
        try:
            result, _ = run_pre_breakout_monthly_validation(
                ROOT / "output" / "release" / "backtest_data.json",
                ROOT / "output" / "pre_breakout",
                month,
            )
            build_dashboard()
            self._json(200, {
                "message": "급등 전 후보 월간 검증 완료",
                "trades": result["summary"]["trades"],
                "win_rate": result["summary"]["win_rate"],
            })
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"급등 전 후보 월간 검증 실패: {exc}"})
        finally:
            RUN_LOCK.release()

    def _json(self, status: int, payload: dict[str, object]) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dashboard] {format % args}")


def _latest_completed_weekday(now: datetime | None = None) -> date:
    now = now or datetime.now()
    market_data_cutoff = now.replace(
        hour=15,
        minute=40,
        second=0,
        microsecond=0,
    )
    candidate = (
        now.date()
        if now >= market_data_cutoff
        else now.date() - timedelta(days=1)
    )
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _set_active_task(task: str) -> None:
    ACTIVE_TASK.clear()
    ACTIVE_TASK.update({
        "task": task,
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })


def _clear_active_task() -> None:
    ACTIVE_TASK.clear()


def _save_operational_entry_snapshot(
    prices: dict[str, dict],
    now: datetime | None = None,
) -> dict | None:
    """Persist selected S80 quotes obtained during the 09:50–10:10 window."""
    now = (now or datetime.now().astimezone()).astimezone()
    minute = now.hour * 60 + now.minute
    if not 9 * 60 + 50 <= minute <= 10 * 60 + 10:
        return None
    runs = PilotHistoryRepository(ROOT / "output" / "kis_v1_1" / "runs").load_all()
    runs = [
        run for run in runs
        if run.get("strategy_version") == OPERATIONAL_VERSION
        and run.get("status") == "PASS"
        and run.get("selected_candidates")
    ]
    if not runs:
        return None
    run = max(runs, key=lambda item: str(item.get("as_of", "")))
    selected = {
        str(item["code"]).zfill(6): {**item, "cohort": "SELECTED"}
        for item in run.get("selected_candidates", [])
    }
    observed = {
        str(item["code"]).zfill(6): {**item, "cohort": "OBSERVATION"}
        for item in run.get("observation_candidates", [])
    }
    tracked = {**observed, **selected}
    candidates = []
    for code, quote in prices.items():
        if code not in tracked:
            continue
        candidate = tracked[code]
        is_observation = candidate["cohort"] == "OBSERVATION"
        gap_allowed = (
            quote.get("change_rate") is not None
            and float(quote["change_rate"]) <= 0.03
        )
        candidates.append({
            "code": code,
            "name": candidate.get("name", code),
            "score": candidate.get("total_score"),
            "cohort": candidate["cohort"],
            "hypothetical_entry": is_observation,
            "selection_date": str(run["as_of"])[:10],
            "entry_price": quote.get("close"),
            "change_rate": quote.get("change_rate"),
            "quote_time": quote.get("time"),
            "entry_allowed": gap_allowed if not is_observation else False,
            "exclusion_reason": (
                "OBSERVATION_HYPOTHETICAL_ONLY" if is_observation
                else None if gap_allowed else "ENTRY_GAP_ABOVE_3_PERCENT"
            ),
        })
    if not candidates:
        return None
    payload = {
        "executed_at": now.isoformat(timespec="seconds"),
        "snapshot_phase": "ENTRY",
        "strategy_version": OPERATIONAL_VERSION,
        "source_run_id": run.get("run_id"),
        "shadow_only": True,
        "entry_rule": "selected: change rate <= +3%; observation: hypothetical only",
        "candidates": candidates,
    }
    output_dir = ROOT / "output" / "kis_v1_1" / "entry_snapshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / now.strftime("%Y%m%dT%H%M%S.json")
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "path": str(output_path.relative_to(ROOT)),
        "candidate_count": len(candidates),
    }


def _news_urls(name: str) -> tuple[str, str, str]:
    query = f"intitle:{name} when:2d"
    encoded = quote_plus(query)
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    )
    search_url = (
        "https://news.google.com/search"
        f"?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    )
    return query, rss_url, search_url


def _fetch_news_headlines(
    rss_url: str,
    limit: int = 12,
) -> list[dict[str, str]]:
    response = httpx.get(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 TITAN-News-Title-Check/1.0"},
        timeout=10.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return _parse_google_news_rss(response.content, limit=limit)


def _discover_market_event_headlines(
    names: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    queries = (
        "실적 OR 어닝서프라이즈 when:1d",
        "수주 OR 공급계약 OR 매출계약 when:1d",
        "승인 OR 허가 OR 자사주소각 OR 목표가상향 when:1d",
    )
    headlines: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = [
            executor.submit(
                _fetch_news_headlines,
                (
                    "https://news.google.com/rss/search"
                    f"?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
                ),
                100,
            )
            for query in queries
        ]
        for future in as_completed(pending):
            try:
                headlines.extend(future.result())
            except (ElementTree.ParseError, httpx.HTTPError):
                continue
    matched: dict[str, list[dict[str, str]]] = {}
    for code, name in names.items():
        if len(name) < 3:
            continue
        rows = [item for item in headlines if name in item["title"]]
        if rows:
            matched[code] = list(
                {
                    (item["title"], item["url"]): item
                    for item in rows
                }.values()
            )
    return matched


def _parse_google_news_rss(
    content: bytes,
    limit: int = 12,
) -> list[dict[str, str]]:
    root = ElementTree.fromstring(content)
    headlines: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published_at = (item.findtext("pubDate") or "").strip()
        source_node = item.find("source")
        source = (
            (source_node.text or "").strip()
            if source_node is not None else ""
        )
        identity = (title, link)
        if not title or not link or identity in seen:
            continue
        seen.add(identity)
        headlines.append(
            {
                "title": title,
                "source": source,
                "published_at": published_at,
                "url": link,
            }
        )
        if len(headlines) >= limit:
            break
    return headlines


def _parse_operational_selection_date(
    value: object,
    now: datetime | None = None,
) -> date:
    if not value:
        raise ValueError("선정 기준일을 입력해 주세요.")
    try:
        target = date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("선정 기준일은 YYYY-MM-DD 형식이어야 합니다.") from exc
    if target.weekday() >= 5:
        raise ValueError("주말은 선정 기준일로 사용할 수 없습니다.")
    latest = _latest_completed_weekday(now)
    if target > latest:
        raise ValueError(
            f"일봉이 완료된 날짜({latest.isoformat()})까지만 선택할 수 있습니다."
        )
    return target


def _parse_exit_rates(payload: dict) -> tuple[float | None, float | None]:
    raw_target = payload.get("profit_target")
    raw_stop = payload.get("stop_loss")
    if raw_target in (None, "") and raw_stop in (None, ""):
        return None, None
    if raw_target in (None, "") or raw_stop in (None, ""):
        raise ValueError("익절률과 손절률을 모두 입력해야 합니다.")
    target = float(raw_target)
    stop = float(raw_stop)
    if not 0 < target <= 100:
        raise ValueError("익절률은 0% 초과 100% 이하여야 합니다.")
    if not 0 < stop <= 100:
        raise ValueError("손절률은 0% 초과 100% 이하여야 합니다.")
    return target / 100, stop / 100


def _parse_entry_settings(
    payload: dict,
) -> tuple[str, float, float | None]:
    mode = payload.get("entry_mode", "OPEN")
    if mode not in {"OPEN", "KIS_1000_LIMIT"}:
        raise ValueError(f"지원하지 않는 매수 방식입니다: {mode}")
    raw_limit = payload.get("entry_limit", 3)
    limit = float(raw_limit)
    if not 0 <= limit <= 100:
        raise ValueError("매수 상한은 0% 이상 100% 이하여야 합니다.")
    raw_minimum = payload.get("entry_minimum")
    if raw_minimum in (None, ""):
        minimum = None
    else:
        minimum_percent = float(raw_minimum)
        if not -100 <= minimum_percent <= 0:
            raise ValueError("매수 하한은 -100% 이상 0% 이하여야 합니다.")
        minimum = minimum_percent / 100
    return mode, limit / 100, minimum


def _latest_kis_test_date(now: datetime | None = None) -> date:
    now = now or datetime.now()
    candidate = (
        now.date()
        if now.time() >= datetime.strptime("15:40", "%H:%M").time()
        else now.date() - timedelta(days=1)
    )
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _find_cached_operational_selection(
    run_dir: Path, selection_date: date
) -> dict | None:
    """Return the newest successful operational result for the date."""
    strategy = "V1.3-S80-N7-TP5-SL10-CANDIDATE"
    matches = []
    for run in PilotHistoryRepository(run_dir).load_all():
        try:
            run_date = datetime.fromisoformat(str(run["as_of"])).date()
        except (KeyError, TypeError, ValueError):
            continue
        if (
            run_date == selection_date
            and run.get("strategy_version") == strategy
            and run.get("status") == "PASS"
        ):
            matches.append(run)
    if not matches:
        return None
    return max(matches, key=lambda run: float(run.get("_file_mtime", 0)))


def _weekdays_between(start: date, end: date) -> int:
    current = start + timedelta(days=1)
    count = 0
    while current <= end:
        count += current.weekday() < 5
        current += timedelta(days=1)
    return count


def main() -> None:
    build_dashboard()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"TITAN dashboard: {url}")
    print("종료: Ctrl+C")
    if os.getenv("TITAN_EVENT_AUTO", "1") != "0":
        threading.Thread(
            target=_event_snapshot_scheduler,
            name="event-snapshot-scheduler",
            daemon=True,
        ).start()
        print("이벤트 모의 스냅샷: 평일 09:30, 10:00 자동 실행")
    if os.getenv("TITAN_NO_BROWSER") != "1":
        threading.Timer(0.7, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _event_snapshot_scheduler() -> None:
    """Trigger preview and entry snapshots while the local server is running."""
    triggered: set[tuple[str, str]] = set()
    while True:
        now = datetime.now().astimezone()
        if now.weekday() < 5:
            for label, hour, minute, window_minutes in (
                ("PREVIEW", 9, 30, 5),
                ("ENTRY", 10, 0, 5),
            ):
                key = (now.date().isoformat(), label)
                elapsed = (
                    now.hour * 60 + now.minute - (hour * 60 + minute)
                )
                if 0 <= elapsed < window_minutes and key not in triggered:
                    triggered.add(key)
                    try:
                        httpx.post(
                            f"http://{HOST}:{PORT}/api/run-event-candidates",
                            json={"automatic": True},
                            timeout=900,
                        )
                    except httpx.HTTPError as exc:
                        print(f"이벤트 {label} 자동 스냅샷 실패: {exc}")
        # Bound memory when the server stays up for months.
        today = now.date().isoformat()
        triggered = {key for key in triggered if key[0] >= today}
        threading.Event().wait(30)


if __name__ == "__main__":
    main()
