# """
# Indicator Domain Model
# """

# from dataclasses import dataclass


# @dataclass(slots=True)
# class IndicatorResult:
#     """
#     기술지표 계산 결과
#     """

#     ma5: float
#     ma20: float
#     ma60: float

#     volume_ratio: float

#     trading_value: float
#     trading_value_ma20: float
#     trading_value_ratio: float

#     change_5d: float
#     change_20d: float

#     high_60: float
#     breakout_ratio: float