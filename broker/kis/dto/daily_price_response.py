from dataclasses import dataclass

from broker.kis.dto.daily_price_dto import DailyPriceDto

@dataclass(slots=True)
class DailyPriceResponse:

    prices: list[DailyPriceDto]