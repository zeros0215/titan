from abc import ABC
from abc import abstractmethod

from domain.candle_series import CandleSeries


class BaseCalculator(ABC):

    @abstractmethod
    def calculate(self, series: CandleSeries):
        pass