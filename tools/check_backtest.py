from broker.mock.market import MockMarketProvider

from domain.stock import Stock
from domain.enums import MarketType

from backtest.engine import BacktestEngine

from strategy.titan_score_strategy import TitanScoreStrategy


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


    engine = BacktestEngine()


    result = engine.run(

        series,

        TitanScoreStrategy()

    )


    print("======================")

    print(
        "TRADES:",
        result.total_trades
    )


    print(
        "TOTAL RETURN:",
        f"{result.total_return:.2f}%"
    )


    print(
        "WIN RATE:",
        f"{result.win_rate:.2f}%"
    )


    print(
        "AVG RETURN:",
        f"{result.average_return:.2f}%"
    )


    print(
        "PROFIT FACTOR:",
        f"{result.profit_factor:.2f}"
    )


    print(
        "AVG HOLD DAYS:",
        f"{result.avg_holding_days:.1f}"
    )

    print(
        "FINAL EQUITY:",
        f"{result.final_equity:,.0f}"
    )


    print(
        "MAX DRAWDOWN:",
        f"{result.max_drawdown:.2f}%"
    )

if __name__ == "__main__":

    main()