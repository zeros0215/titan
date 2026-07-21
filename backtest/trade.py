from dataclasses import dataclass
from datetime import datetime



@dataclass(slots=True)
class Trade:


    symbol: str

    buy_date: datetime

    buy_price: float


    sell_date: datetime | None = None

    sell_price: float | None = None

    entry_index: int = 0

    @property
    def is_closed(self) -> bool:

        return self.sell_price is not None



    @property
    def return_rate(self) -> float:


        if not self.is_closed:

            return 0.0



        return (

            (
                self.sell_price
                -
                self.buy_price
            )

            /

            self.buy_price

            *

            100

        )