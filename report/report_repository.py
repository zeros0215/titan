"""
TITAN Report Repository
"""


import json
from pathlib import Path



class ReportRepository:


    def __init__(

        self,

        path="reports"

    ):


        self.path = Path(path)

        self.path.mkdir(

            exist_ok=True

        )



    def save(

        self,

        filename,

        data

    ):


        file = self.path / filename


        with open(

            file,

            "w",

            encoding="utf-8"

        ) as f:


            json.dump(

                data,

                f,

                ensure_ascii=False,

                indent=4

            )


        return file