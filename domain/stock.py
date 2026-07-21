"""
Stock Domain Model
"""

from dataclasses import dataclass

from domain.enums import MarketType


@dataclass(slots=True)
class Stock:

    code: str

    name: str

    market: MarketType

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"