"""
Stock Repository
"""

from pathlib import Path
import csv

from domain.stock import Stock


class StockRepository:

    def __init__(self):

        self.market_dir = (

            Path(__file__).resolve().parent.parent

            / "resources"

            / "market"

        )

    def get_all(self) -> list[Stock]:

        stocks = []

        for file_name in (

            "kospi.csv",

            "kosdaq.csv"

        ):

            stocks.extend(

                self._load_csv(file_name)

            )

        return stocks

    def _load_csv(

        self,

        file_name: str

    ) -> list[Stock]:

        path = self.market_dir / file_name

        result = []

        with open(

            path,

            encoding="utf-8"

        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                result.append(

                    Stock(

                        code=row["code"],

                        name=row["name"],

                        market=row["market"]

                    )

                )

        return result