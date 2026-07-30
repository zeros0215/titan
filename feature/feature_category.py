from enum import Enum


class FeatureCategory(Enum):
    """
    Feature 상위 분류
    """

    TREND = "TREND"

    MOMENTUM = "MOMENTUM"

    VOLUME = "VOLUME"

    PRICE_ACTION = "PRICE_ACTION"

    RISK = "RISK"