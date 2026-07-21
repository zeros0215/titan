"""
TITAN Score Engine
"""

from indicators.bundle import IndicatorBundle

from scoring.result import ScoreResult
from scoring.grade import calculate_grade

from config.score_config import ScorePolicy


class ScoreEngine:


    def calculate(

        self,

        indicators: IndicatorBundle

    ) -> ScoreResult:


        trend = self._trend_score(
            indicators
        )


        volume = self._volume_score(
            indicators
        )


        trading = self._trading_score(
            indicators
        )


        momentum = self._momentum_score(
            indicators
        )


        breakout = self._breakout_score(
            indicators
        )


        risk = self._risk_penalty(
            indicators
        )


        #
        # Raw Score
        #
        raw_score = max(

            trend
            + volume
            + trading
            + momentum
            + breakout
            - risk,

            0

        )


        #
        # 현재는 Raw Score를 최종 점수로 사용
        #
        # 추후 종목군별 Weight 적용 후
        # Normalization 추가
        #
        normalized_score = min(

            raw_score,

            100

        )

        print(
        f"""
        [SCORE DEBUG]

        Trend    : {trend}
        Volume   : {volume}
        Trading  : {trading}
        Momentum : {momentum}
        Breakout : {breakout}
        Risk     : {risk}

        RAW      : {raw_score}
        NORMAL   : {normalized_score}

        """
        )
        return ScoreResult(

            trend_score=trend,

            volume_score=volume,

            trading_score=trading,

            momentum_score=momentum,

            breakout_score=breakout,

            risk_penalty=risk,


            raw_score=raw_score,


            normalized_score=normalized_score,


            grade=calculate_grade(

                normalized_score

            )

        )



    def _trend_score(

        self,

        indicators

    ):


        ma = indicators.moving_average


        score = 0


        if ma.price_above_ma20:

            score += ScorePolicy.PRICE_ABOVE_MA20


        if ma.ma5_above_ma20:

            score += ScorePolicy.MA5_ABOVE_MA20


        if ma.ma20_above_ma60:

            score += ScorePolicy.MA20_ABOVE_MA60


        return score



    def _volume_score(

        self,

        indicators

    ):


        ratio = indicators.volume.volume_ratio


        if ratio >= 1.5:

            return ScorePolicy.VOLUME_RATIO_HIGH


        elif ratio >= 1.3:

            return ScorePolicy.VOLUME_RATIO_MID


        elif ratio >= 1.1:

            return ScorePolicy.VOLUME_RATIO_LOW


        return 0



    def _trading_score(

        self,

        indicators

    ):


        ratio = indicators.volume.trading_value_ratio


        if ratio >= 1.5:

            return ScorePolicy.TRADING_HIGH


        elif ratio >= 1.2:

            return ScorePolicy.TRADING_MID


        elif ratio >= 1.0:

            return ScorePolicy.TRADING_LOW


        return 0



    def _momentum_score(

        self,

        indicators

    ):


        result = 0


        m = indicators.momentum



        #
        # 5일 Momentum
        #
        if m.change_5d >= 0.10:

            result += ScorePolicy.MOMENTUM_5D_HIGH


        elif m.change_5d >= 0.07:

            result += ScorePolicy.MOMENTUM_5D_MID


        elif m.change_5d >= 0.03:

            result += ScorePolicy.MOMENTUM_5D_LOW



        #
        # 20일 Momentum
        #
        if m.change_20d >= 0.2:

            result += ScorePolicy.MOMENTUM_20D_HIGH


        elif m.change_20d >= 0.1:

            result += ScorePolicy.MOMENTUM_20D_MID



        #
        # RSI
        #
        rsi = indicators.rsi


        if rsi <= 30:

            result += ScorePolicy.RSI_OVERSOLD_BONUS


        elif 50 <= rsi < 70:

            result += ScorePolicy.RSI_TREND_BONUS


        elif rsi >= 70:

            result -= ScorePolicy.RSI_OVERHEAT_PENALTY



        return result



    def _breakout_score(

        self,

        indicators

    ):


        ratio = indicators.breakout.price_position


        if ratio >= 0.95:

            return ScorePolicy.BREAKOUT_HIGH


        elif ratio >= 0.90:

            return ScorePolicy.BREAKOUT_LOW


        return 0



    def _risk_penalty(

        self,

        indicators

    ):


        change = indicators.risk.change_20d


        if change <= -0.15:

            return ScorePolicy.RISK_HIGH_PENALTY


        elif change < 0:

            return ScorePolicy.RISK_LOW_PENALTY


        return 0