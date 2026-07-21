"""
Market Updater
"""

from pathlib import Path
import csv

from market.ProviderFactory import ProviderFactory


class MarketUpdater:

    def __init__(self):

        self.downloader = ProviderFactory.create()

        self.output_dir = (
            Path(__file__).resolve().parent.parent
            / "resources"
            / "market"
        )

    def update(self):

        rows = self.downloader.download()

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        path = self.output_dir / "stocks.csv"

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.writer(file)

            writer.writerow(
                [
                    "code",
                    "name",
                    "market"
                ]
            )

            for row in rows:

                writer.writerow(
                    [
                        row["code"],
                        row["name"],
                        row["market"]
                    ]
                )

        print(f"{len(rows)} stocks saved.")

        print(path)