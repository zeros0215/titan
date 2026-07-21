"""
RSI Indicator
"""

from domain.candle_series import CandleSeries


def calculate(
    series: CandleSeries,
    period: int = 14
) -> float:

    closes = series.closes

    if len(closes) <= period:
        return 50.0


    gains = []
    losses = []


    for i in range(1, len(closes)):

        diff = closes[i] - closes[i - 1]


        if diff >= 0:
            gains.append(diff)
            losses.append(0)

        else:
            gains.append(0)
            losses.append(abs(diff))


    recent_gains = gains[-period:]
    recent_losses = losses[-period:]


    avg_gain = sum(recent_gains) / period
    avg_loss = sum(recent_losses) / period


    if avg_loss == 0:
        return 100.0


    rs = avg_gain / avg_loss


    return round(
        100 - (100 / (1 + rs)),
        2
    )