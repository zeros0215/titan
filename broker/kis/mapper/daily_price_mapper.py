"""
Daily Price Mapper
"""

from broker.kis.dto.daily_price_dto import DailyPriceDto


class DailyPriceMapper:

    @staticmethod
    def to_list(data: dict) -> list[DailyPriceDto]:

        return [

            DailyPriceDto(

                date=item["stck_bsop_date"],

                open=int(item["stck_oprc"]),

                high=int(item["stck_hgpr"]),

                low=int(item["stck_lwpr"]),

                close=int(item["stck_clpr"]),

                volume=int(item["acml_vol"])

            )

            for item in data["output2"]

        ]