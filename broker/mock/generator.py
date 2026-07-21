"""
Mock Candle Generator
"""

from datetime import datetime
from datetime import timedelta

import random


from domain.candle import Candle

from domain.candle_series import CandleSeries

from domain.stock import Stock



class MockGenerator:


    @staticmethod
    def create(

        stock: Stock,

        count: int = 100

    ) -> CandleSeries:


        candles = []


        base_price = 70000


        today = datetime.now()


        for i in range(count):


            date = (

                today

                -

                timedelta(

                    days=count-i

                )

            )


            change = random.uniform(

                -0.03,

                0.03

            )


            open_price = base_price


            close_price = (

                base_price

                *

                (1 + change)

            )


            high_price = max(

                open_price,

                close_price

            ) * 1.01


            low_price = min(

                open_price,

                close_price

            ) * 0.99



            volume = random.randint(

                1000000,

                5000000

            )


            candles.append(

                Candle(

                    date=date,

                    open=open_price,

                    high=high_price,

                    low=low_price,

                    close=close_price,

                    volume=volume

                )

            )


            base_price = close_price



        return CandleSeries(

            stock=stock,

            candles=candles

        )