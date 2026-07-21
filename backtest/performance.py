"""
TITAN Performance Analyzer
"""


class PerformanceAnalyzer:



    def max_drawdown(

        self,

        equity_curve

    ):


        if not equity_curve:

            return 0.0



        return min(

            item["drawdown"]

            for item in equity_curve

        )



    def final_equity(

        self,

        equity_curve

    ):


        if not equity_curve:

            return 0.0



        return equity_curve[-1]["capital"]