from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryScore:
    """
    카테고리별 점수
    """

    trend: float = 0.0

    momentum: float = 0.0

    volume: float = 0.0

    price_action: float = 0.0

    risk: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.trend
            + self.momentum
            + self.volume
            + self.price_action
            + self.risk
        )