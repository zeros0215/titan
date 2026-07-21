"""
KIS Candle Mapper
"""

from datetime import datetime

from broker.kis.dto.daily_price_dto import DailyPriceDto

from domain.candle import Candle


class CandleMapper:

    @staticmethod
    def to_domain(
        dto: DailyPriceDto
    ) -> Candle:

        return Candle(

            date=datetime.strptime(
                dto.date,
                "%Y%m%d"
            ),

            open=float(dto.open),

            high=float(dto.high),

            low=float(dto.low),

            close=float(dto.close),

            volume=dto.volume

        )

    @staticmethod
    def to_domain_list(
        dto_list: list[DailyPriceDto]
    ) -> list[Candle]:

        return [

            CandleMapper.to_domain(dto)

            for dto in dto_list

        ]