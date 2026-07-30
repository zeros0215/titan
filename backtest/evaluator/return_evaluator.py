from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ReturnEvaluator:
    """
    수익률 계산기.

    Selection의 성과를 계산하는 역할만 담당한다.
    """

    def evaluate(
        self,
        selection_price: float,
        evaluation_price: float,
    ) -> float:
        """
        수익률 계산

        Returns
        -------
        float
            0.15 = +15%
        """

        if selection_price <= 0:
            raise ValueError("selection_price must be greater than zero")

        if evaluation_price < 0:
            raise ValueError("evaluation_price must not be negative")

        return (
            evaluation_price - selection_price
        ) / selection_price
