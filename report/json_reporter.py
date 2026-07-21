"""
TITAN JSON Reporter
"""

import json
from dataclasses import asdict

from analysis.result import AnalysisResult



class JsonReporter:


    def to_dict(

        self,

        result: AnalysisResult

    ):


        return {

            "stock": {

                "code": result.stock.code,

                "name": result.stock.name

            },


            "score": {

                "raw": result.score.raw_score,

                "normalized":
                    result.score.normalized_score,

                "grade":
                    result.score.grade,


                "detail": {

                    "trend":
                        result.score.trend_score,

                    "volume":
                        result.score.volume_score,

                    "trading":
                        result.score.trading_score,

                    "momentum":
                        result.score.momentum_score,

                    "breakout":
                        result.score.breakout_score,

                    "risk":
                        result.score.risk_penalty

                }

            },


            "recommendation":
                result.recommendation,


            "positive":

                result.positive_factors,


            "negative":

                result.negative_factors

        }



    def to_json(

        self,

        result: AnalysisResult

    ):


        return json.dumps(

            self.to_dict(result),

            ensure_ascii=False,

            indent=4

        )