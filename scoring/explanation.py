"""
TITAN Score Explanation
"""


from indicators.bundle import IndicatorBundle


class ScoreExplanation:


    @staticmethod
    def build(
        indicators: IndicatorBundle
    ) -> list[str]:

        reasons = []


        #
        # Trend
        #
        ma = indicators.moving_average

        if ma.price_above_ma20:

            reasons.append(
                "Price above MA20"
            )


        if ma.ma5_above_ma20:

            reasons.append(
                "MA5 above MA20"
            )


        if ma.ma20_above_ma60:

            reasons.append(
                "MA20 above MA60"
            )


        #
        # Volume
        #
        if indicators.volume.volume_ratio >= 1.5:

            reasons.append(
                "Strong volume increase"
            )


        #
        # Momentum
        #
        m = indicators.momentum

        if m.change_5d >= 0.07:

            reasons.append(
                "Short term momentum positive"
            )


        if m.change_20d >= 0.10:

            reasons.append(
                "20 day momentum positive"
            )


        #
        # RSI
        #
        rsi = indicators.rsi


        if rsi <= 30:

            reasons.append(
                f"RSI oversold ({rsi})"
            )


        elif 50 <= rsi < 70:

            reasons.append(
                f"RSI healthy zone ({rsi})"
            )


        elif rsi >= 70:

            reasons.append(
                f"RSI overheat ({rsi})"
            )


        #
        # Breakout
        #
        if indicators.breakout.price_position >= 0.95:

            reasons.append(
                "Near breakout zone"
            )


        return reasons