"""
Stock Domain Model
"""

from dataclasses import dataclass

from domain.enums import MarketType
from datetime import datetime


@dataclass(slots=True)
class Stock:

    code: str

    name: str

    market: MarketType

    effective_from: datetime | None = None

    effective_to: datetime | None = None

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"
