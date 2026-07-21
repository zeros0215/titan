"""
TITAN Console Reporter
"""


class ConsoleReporter:


    def report(
        self,
        results
    ):

        print()

        print("=" * 60)
        print("TITAN ANALYSIS REPORT")
        print("=" * 60)


        if not results:

            print(
                "No stocks found."
            )

            return



        for index, item in enumerate(
            results,
            start=1
        ):


            stock = item.stock

            score = item.score


            print()

            print(
                f"Rank : {index}"
            )

            print(
                f"Code : {stock.code}"
            )

            print(
                f"Name : {stock.name}"
            )


            print()

            print(
                f"Score : {score.normalized_score} / 100"
            )


            print(
                f"Grade : {score.grade}"
            )


            print(
                f"Decision : {item.recommendation}"
            )

            print()


            print("[ SCORE ]")

            print(
                f"Trend      : {score.trend_score}"
            )

            print(
                f"Volume     : {score.volume_score}"
            )

            print(
                f"Trading    : {score.trading_score}"
            )

            print(
                f"Momentum   : {score.momentum_score}"
            )

            print(
                f"Breakout   : {score.breakout_score}"
            )

            print(
                f"Risk       : {score.risk_penalty}"
            )


            print()


            print("[ POSITIVE ]")


            for p in item.positive_factors:

                print(
                    f"+ {p}"
                )


            print()


            print("[ NEGATIVE ]")


            for n in item.negative_factors:

                print(
                    f"- {n}"
                )


            print()

            print("-" * 60)