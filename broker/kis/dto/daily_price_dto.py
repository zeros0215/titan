from dataclasses import dataclass


@dataclass(slots=True)
class DailyPriceDto:

    date: str

    open: int

    high: int

    low: int

    close: int

    volume: int