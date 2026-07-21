"""
TITAN Equity Curve
"""


class EquityCurve:


    def calculate(

        self,

        equity_data

    ):


        if not equity_data:

            return []



        curve = []


        peak = equity_data[0]["capital"]



        for item in equity_data:


            capital = item["capital"]



            #
            # 최고점 갱신
            #
            if capital > peak:

                peak = capital



            #
            # Drawdown 계산
            #
            drawdown = (

                capital

                -

                peak

            ) / peak * 100



            curve.append(

                {

                    "date": item["date"],

                    "capital": capital,

                    "drawdown": drawdown

                }

            )


        return curve