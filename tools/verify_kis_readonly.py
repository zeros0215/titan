"""Minimal read-only KIS production-path verification.

Never prints credentials, access tokens, or raw HTTP bodies.
"""

import argparse
import json
from datetime import datetime, timedelta

from benchmark.kis import KisBenchmarkProvider
from broker.kis.market import KisMarketProvider
from broker.kis.session import KisSession
from data.quality import CandleSeriesValidator
from domain.enums import MarketType
from domain.stock import Stock
from operation.holiday import KisHolidayProvider
from broker.kis.exception import KisApiException


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-code", default="005930")
    parser.add_argument("--stock-name", default="Samsung Electronics")
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args(argv)
    if args.days < 90:
        raise ValueError("days must be at least 90 for quality verification")

    end = datetime.now()
    start = end - timedelta(days=args.days)
    session = KisSession()
    result = {
        "mode": "READ_ONLY",
        "token": "NOT_CHECKED",
        "holiday": {},
        "benchmarks": {},
        "stock": {},
    }
    try:
        token = session.auth.get_token()
        result["token"] = (
            "OK" if token.access_token and not token.is_expired else "INVALID"
        )

        try:
            sessions = KisHolidayProvider(session).get_sessions(
                end.date(),
                (end + timedelta(days=30)).date(),
            )
            result["holiday"] = {
                "status": "OK",
                "row_count": len(sessions),
                "open_count": sum(sessions.values()),
            }
        except KisApiException as error:
            result["holiday"] = {
                "status": (
                    "UNSUPPORTED_IN_VIRTUAL"
                    if error.code == "EGW02006"
                    else "FAILED"
                ),
                "error_code": error.code,
            }

        try:
            returns = KisBenchmarkProvider(session=session).get_returns(
                {MarketType.KOSPI, MarketType.KOSDAQ},
                start,
                end,
            )
            result["benchmarks"] = {
                "status": "OK",
                "markets": sorted(returns),
                "finite": all(
                    isinstance(value, float)
                    and value == value
                    and abs(value) < 10
                    for value in returns.values()
                ),
            }
        except Exception as error:
            result["benchmarks"] = {
                "status": "FAILED",
                "error_type": type(error).__name__,
                "error": str(error),
            }

        try:
            stock = Stock(args.stock_code, args.stock_name, MarketType.KOSPI)
            series = KisMarketProvider(session=session).get_daily_prices(
                stock,
                start,
                end,
            )
            quality = CandleSeriesValidator(minimum_candles=61).validate(series)
            candles = series.candles
            result["stock"] = {
                "status": "OK",
                "code": args.stock_code,
                "candle_count": len(candles),
                "first_date": (
                    candles[0].date.date().isoformat() if candles else None
                ),
                "last_date": (
                    candles[-1].date.date().isoformat() if candles else None
                ),
                "quality_valid": quality.is_valid,
                "quality_warnings": [
                    issue.code
                    for issue in quality.issues
                    if issue.severity.value == "WARNING"
                ],
                "quality_errors": [
                    issue.code
                    for issue in quality.issues
                    if issue.severity.value == "ERROR"
                ],
            }
        except Exception as error:
            result["stock"] = {
                "status": "FAILED",
                "error_type": type(error).__name__,
                "error": str(error),
            }
    except Exception as error:
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    finally:
        session.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (
        result["token"] == "OK"
        and result["holiday"].get("status")
        in {"OK", "UNSUPPORTED_IN_VIRTUAL"}
        and result["benchmarks"].get("finite") is True
        and result["stock"].get("quality_valid") is True
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
