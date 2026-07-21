"""
TITAN Score Policy

Maximum Score 기준

Trend       40
Momentum    30
Breakout    20
Volume      15
Trading     10
Risk       -20

Total       100+
"""


class ScorePolicy:


    #
    # Trend
    #
    # 가장 중요한 영역
    #
    PRICE_ABOVE_MA20 = 15

    MA5_ABOVE_MA20 = 15

    MA20_ABOVE_MA60 = 10



    #
    # Volume
    #
    # 거래량은 보조 확인
    #
    VOLUME_RATIO_HIGH = 15

    VOLUME_RATIO_MID = 10

    VOLUME_RATIO_LOW = 5



    #
    # Trading Value
    #
    # 유동성 확인 목적
    #
    TRADING_HIGH = 10

    TRADING_MID = 7

    TRADING_LOW = 5



    #
    # Momentum
    #
    # 상승 힘
    #
    MOMENTUM_5D_HIGH = 15

    MOMENTUM_5D_MID = 10

    MOMENTUM_5D_LOW = 5


    MOMENTUM_20D_HIGH = 15

    MOMENTUM_20D_MID = 10



    #
    # Breakout
    #
    # 신고가/돌파
    #
    BREAKOUT_HIGH = 20

    BREAKOUT_LOW = 10



    #
    # RSI
    #
    RSI_OVERSOLD_BONUS = 5

    RSI_TREND_BONUS = 5

    RSI_OVERHEAT_PENALTY = 10



    #
    # Risk
    #
    RISK_HIGH_PENALTY = 20

    RISK_LOW_PENALTY = 10



    #
    # Grade
    #
    GRADE_S = 90

    GRADE_A = 70

    GRADE_B = 50

    GRADE_C = 30