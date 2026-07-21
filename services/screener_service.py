"""
Screener Service
"""

from screener.engine import ScreenerEngine


class ScreenerService:

    def __init__(self):

        self.engine = ScreenerEngine()

    def run(

        self,

        histories

    ):

        return self.engine.run(

            histories

        )