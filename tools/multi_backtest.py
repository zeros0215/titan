"""
TITAN Multi Stock Backtest Runner
"""


from broker.mock.market import MockMarketProvider

from domain.stock import Stock
from domain.enums import MarketType

from backtest.engine import BacktestEngine
from strategy.titan_score_strategy import TitanScoreStrategy
from backtest.performance_score import PerformanceScore


STOCKS = [

    ("005930", "Samsung Electronics"),

    ("000660", "SK Hynix"),

    ("035420", "NAVER"),

    ("005380", "Hyundai Motor"),

    ("105560", "KB Financial"),

    ("068270", "Celltrion"),

]



def main():


    provider = MockMarketProvider()


    engine = BacktestEngine()



    results = []

    scorer = PerformanceScore()

    print("=" * 50)

    print("TITAN MULTI STOCK BACKTEST")

    print("=" * 50)



    for code, name in STOCKS:


        stock = Stock(

            code=code,

            name=name,

            market=MarketType.KOSPI

        )


        series = provider.get_daily_price(

            stock

        )


        strategy = TitanScoreStrategy()


        result = engine.run(

            series,

            strategy

        )


        results.append(

            {

                "code": code,

                "name": name,

                "result": result,

                "score": scorer.calculate(result)

            }

        )



        print()

        print(

            code,

            name

        )

        print(

            "TRADES:",

            len(result.trades)

        )

        print(

            "RETURN:",

            f"{result.total_return:.2f}%"

        )

        print(

            "MDD:",

            f"{result.max_drawdown:.2f}%"

        )

        print(

            "PF:",

            result.profit_factor

        )





    #
    # Ranking
    #
    print()

    print("=" * 50)

    print("TITAN PERFORMANCE RANKING")

    print("=" * 50)



    ranking = sorted(

        results,

        key=lambda x:

            x["score"],

        reverse=True

    )


    for index, item in enumerate(

        ranking,

        start=1

    ):


        result = item["result"]


        print(

            f"{index}. "

            f"{item['code']} "

            f"{item['name']} "

            f"SCORE:{item['score']} "

            f"RETURN:{result.total_return:.2f}% "

            f"MDD:{result.max_drawdown:.2f}%"

        )




if __name__ == "__main__":

    main()