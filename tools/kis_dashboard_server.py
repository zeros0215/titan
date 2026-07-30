"""Local-only web server for dated KIS read-only pilot tests."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from tools.build_kis_dashboard import LOCAL_INDEX, ROOT, main as build_dashboard
from tools.local_monthly_test import run_month, run_year
from analysis.sector_laggard import run_sector_laggard_backtest


HOST = "127.0.0.1"
PORT = 8765
RUN_LOCK = threading.Lock()


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path not in ("/", "/index.html"):
            self.send_error(404)
            return
        build_dashboard()
        content = LOCAL_INDEX.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
            "/api/run-sector-laggard",
        ):
            self.send_error(404)
            return
        if path == "/api/run-sector-laggard":
            self._run_sector_laggard()
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
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"message": str(exc) or "날짜 형식이 올바르지 않습니다."})
            return

        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
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
            self._json(200, {"message": "완료", "returncode": result.returncode})
        except subprocess.TimeoutExpired:
            self._json(504, {"message": "테스트가 30분 제한시간을 초과했습니다."})
        finally:
            RUN_LOCK.release()

    def _run_month(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            month = datetime.strptime(payload["month"], "%Y-%m").strftime(
                "%Y-%m"
            )
            holding_sessions = int(payload.get("holding_sessions", 1))
            if holding_sessions not in (1, 5, 10, 20):
                raise ValueError
            strategy_version = payload.get("strategy_version", "V1.1")
            if strategy_version not in (
                "V1.1",
                "V1.2-CANDIDATE",
                "V1.2-GAP-CANDIDATE",
                "V1.2-5D-CANDIDATE",
                "V1.3-RISK-5D-CANDIDATE",
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "월은 YYYY-MM 형식이어야 합니다."})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
            results = run_month(
                month,
                holding_sessions=holding_sessions,
                strategy_version=strategy_version,
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

    def _run_year(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            year = datetime.strptime(str(payload["year"]), "%Y").strftime(
                "%Y"
            )
            holding_sessions = int(payload.get("holding_sessions", 1))
            if holding_sessions not in (1, 5, 10, 20):
                raise ValueError
            strategy_version = payload.get("strategy_version", "V1.1")
            if strategy_version not in (
                "V1.1",
                "V1.2-CANDIDATE",
                "V1.2-GAP-CANDIDATE",
                "V1.2-5D-CANDIDATE",
                "V1.3-RISK-5D-CANDIDATE",
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "연도는 YYYY 형식이어야 합니다."})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
            results = run_year(
                year,
                holding_sessions=holding_sessions,
                strategy_version=strategy_version,
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

    def _run_sector_laggard(self) -> None:
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
            result, _ = run_sector_laggard_backtest(
                ROOT / "output" / "release" / "backtest_data.json",
                ROOT / "output" / "sector_laggard",
                start_date=start_date,
                end_date=end_date,
            )
            build_dashboard()
            self._json(
                200,
                {
                    "message": "완료",
                    "raw_trades": result["summaries"]["RAW"]["trades"],
                    "confirmed_trades": result["summaries"]["CONFIRMED"]["trades"],
                },
            )
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"패턴 테스트 실패: {exc}"})
        finally:
            RUN_LOCK.release()

    def _run_momentum_exit(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            end_month = datetime.strptime(
                payload.get("end_month", "2026-06"),
                "%Y-%m",
            ).strftime("%Y-%m")
        except (TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"message": "종료 월은 YYYY-MM 형식이어야 합니다."})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self._json(409, {"message": "다른 테스트가 이미 실행 중입니다."})
            return
        try:
            result, _ = run_sector_laggard_backtest(
                ROOT / "output" / "release" / "backtest_data.json",
                ROOT / "output" / "sector_laggard",
                start_month="2022-04",
                end_month=end_month,
                quantile=0.20,
                holding_sessions=5,
            )
            build_dashboard()
            self._json(
                200,
                {
                    "message": "완료",
                    "all_trades": result["summaries"]["ALL_LEADERS"]["trades"],
                    "v1_3_trades": result["summaries"]["V1_3_FILTERED"]["trades"],
                },
            )
        except ValueError as exc:
            self._json(400, {"message": str(exc)})
        except Exception as exc:
            self._json(500, {"message": f"5거래일 매도 테스트 실패: {exc}"})
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


def main() -> None:
    build_dashboard()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"TITAN dashboard: {url}")
    print("종료: Ctrl+C")
    threading.Timer(0.7, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
