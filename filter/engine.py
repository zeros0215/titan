"""
TITAN Filter Engine
"""

from filter.policy import FilterPolicy


class FilterEngine:


    def filter(

        self,

        results

    ):

        filtered = []


        for item in results:


            score = item.score
            print(
                item.stock.code,
                item.stock.name,
                "RAW:",
                score.raw_score,
                "NORMAL:",
                score.normalized_score,
                "VOL:",
                score.volume_score,
                "TRADING:",
                score.trading_score,
                "MOM:",
                score.momentum_score
            )

            #
            # 최소 점수
            # normalized score 기준
            #
            if (
                score.normalized_score
                < FilterPolicy.MIN_SCORE
            ):

                continue



            #
            # 거래량 조건
            #
            if (

                FilterPolicy.REQUIRE_VOLUME

                and score.volume_score == 0

            ):

                continue



            #
            # 거래대금 조건
            #
            if (

                FilterPolicy.REQUIRE_TRADING

                and score.trading_score == 0

            ):

                continue



            #
            # 모멘텀 조건
            #
            if (

                FilterPolicy.REQUIRE_MOMENTUM

                and score.momentum_score == 0

            ):

                continue



            filtered.append(item)


        return filtered