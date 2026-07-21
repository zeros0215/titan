"""
TITAN Filter Policy
"""


class FilterPolicy:


    #
    # 최소 Score
    #
    # 후보군 확보 목적
    #
    MIN_SCORE = 40



    #
    # 거래량
    #
    # Ranking에서 판단
    #
    REQUIRE_VOLUME = False



    #
    # 거래대금
    #
    REQUIRE_TRADING = False



    #
    # Momentum
    #
    REQUIRE_MOMENTUM = False