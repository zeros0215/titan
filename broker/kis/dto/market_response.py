"""
KIS Daily Price Response DTO
"""

from dataclasses import dataclass

from broker.kis.exception import (
    KisMarketException,
)


@dataclass(slots=True, frozen=True)
class DailyPriceItem:

    date: str

    open: float

    high: float

    low: float

    close: float

    volume: int


@dataclass(slots=True)
class DailyPriceResponse:

    output2: list[DailyPriceItem]

    @classmethod
    def from_json(

        cls,

        data: dict

    ) -> "DailyPriceResponse":

        #
        # API Error
        #
        if data.get("rt_cd") != "0":

            raise KisMarketException(

                data.get(

                    "msg_cd",

                    "UNKNOWN"

                ),

                data.get(

                    "msg1",

                    "Unknown Error"

                )

            )

        items = []

        for row in data.get(

            "output2",

            []

        ):

            items.append(

                DailyPriceItem(

                    date=row["stck_bsop_date"],

                    open=float(row["stck_oprc"]),

                    high=float(row["stck_hgpr"]),

                    low=float(row["stck_lwpr"]),

                    close=float(row["stck_clpr"]),

                    volume=int(row["acml_vol"])

                )

            )

        return cls(items)