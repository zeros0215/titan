"""
Reporter Interface
"""

from abc import ABC
from abc import abstractmethod

from analysis.result import AnalysisResult


class Reporter(ABC):

    @abstractmethod
    def report(
        self,
        ranking: list[AnalysisResult]
    ) -> None:
        pass