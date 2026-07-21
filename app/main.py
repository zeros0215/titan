"""
TITAN Entry Point
"""

from core.container import Container

from report.console_reporter import ConsoleReporter

from config.constants import PROJECT_TITLE, VERSION
from config.settings import settings
from report.csv_reporter import CsvReporter
from core.logger import logger
from datetime import datetime

def banner():

    print("=" * 50)

    print(PROJECT_TITLE)

    print(f"Version : {VERSION}")

    print("=" * 50)


def main():


    stock = Stock(

        code="005930",

        name="Samsung Electronics",

        market=MarketType.KOSPI

    )


    provider = MockMarketProvider()


    series = provider.get_daily_price(
        stock
    )


    strategy = TitanScoreStrategy()


    engine = BacktestEngine()


    result = engine.run(

        series,

        strategy

    )


    print("======================")

    print(
        "TRADES:",
        len(result.trades)
    )


    print(
        "RETURN:",
        result.total_return
    )


    print(
        "WIN RATE:",
        result.win_rate
    )

if __name__ == "__main__":

    main()