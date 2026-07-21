"""
TITAN Analysis Explainer

Indicator 기반 분석 설명 생성
"""


from indicators.bundle import IndicatorBundle
from scoring.result import ScoreResult



class AnalysisExplainer:


    def explain(

        self,

        indicators: IndicatorBundle,

        score: ScoreResult

    ):


        positive = []

        negative = []


        #
        # Trend
        #
        ma = indicators.moving_average


        if ma.price_above_ma20:

            positive.append(
                "현재가가 MA20 상단 위치 (중기 상승 추세)"
            )

        else:

            negative.append(
                "현재가가 MA20 아래 위치 (추세 약화)"
            )


        if ma.ma5_above_ma20:

            positive.append(
                "MA5 > MA20 단기 상승 흐름"
            )

        else:

            negative.append(
                "MA5 < MA20 단기 약세"
            )


        if ma.ma20_above_ma60:

            positive.append(
                "MA20 > MA60 장기 상승 구조"
            )

        else:

            negative.append(
                "MA20 < MA60 장기 추세 약화"
            )



        #
        # Volume
        #
        volume = indicators.volume


        if score.volume_score > 0:

            positive.append(

                f"거래량 증가 "
                f"(비율 {volume.volume_ratio:.2f}배)"

            )

        else:

            negative.append(
                "거래량 증가 신호 부족"
            )



        #
        # Trading Value
        #

        if score.trading_score > 0:

            positive.append(

                f"거래대금 증가 "
                f"(비율 {volume.trading_value_ratio:.2f}배)"

            )

        else:

            negative.append(
                "거래대금 유입 부족"
            )



        #
        # Momentum
        #

        momentum = indicators.momentum


        if momentum.change_5d > 0:

            positive.append(

                f"5일 상승 모멘텀 "
                f"({momentum.change_5d * 100:.1f}%)"

            )

        else:

            negative.append(
                "최근 5일 상승 모멘텀 부족"
            )



        if momentum.change_20d > 0:

            positive.append(

                f"20일 상승 추세 "
                f"({momentum.change_20d * 100:.1f}%)"

            )



        #
        # Breakout
        #

        breakout = indicators.breakout


        if score.breakout_score > 0:

            positive.append(

                f"고점 접근 상태 "
                f"({breakout.price_position * 100:.1f}%)"

            )

        else:

            negative.append(
                "신고가 돌파 신호 부족"
            )



        #
        # RSI
        #

        rsi = indicators.rsi


        if rsi >= 70:

            negative.append(

                f"RSI 과열 구간 "
                f"({rsi:.1f})"

            )


        elif rsi <= 30:

            positive.append(

                f"RSI 저평가 영역 "
                f"({rsi:.1f})"

            )



        #
        # Risk
        #

        if score.risk_penalty > 0:

            negative.append(
                "최근 가격 하락 위험 존재"
            )


        else:

            positive.append(
                "최근 하락 위험 낮음"
            )


        return positive, negative