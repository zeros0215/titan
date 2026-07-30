class ScorePolicy:

    # Trend
    PRICE_ABOVE_MA20 = 15
    MA5_ABOVE_MA20 = 15
    MA20_ABOVE_MA60 = 10

    # Volume
    VOLUME_RATIO_HIGH = 20
    VOLUME_RATIO_MID = 15
    VOLUME_RATIO_LOW = 10

    # Trading Value
    TRADING_HIGH = 20
    TRADING_MID = 15
    TRADING_LOW = 10

    # Momentum
    MOMENTUM_5D_HIGH = 10
    MOMENTUM_5D_MID = 7
    MOMENTUM_5D_LOW = 5

    MOMENTUM_20D_HIGH = 10
    MOMENTUM_20D_MID = 5

    # Breakout
    BREAKOUT_HIGH = 20
    BREAKOUT_LOW = 10

    # Risk
    RISK_HIGH_PENALTY = 20
    RISK_LOW_PENALTY = 10

    # Grade
    GRADE_S = 90
    GRADE_A = 70
    GRADE_B = 50
    GRADE_C = 30