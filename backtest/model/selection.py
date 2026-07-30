from dataclasses import dataclass
from datetime import datetime

from analysis.analysis_result import AnalysisResult


@dataclass(slots=True)
class Selection:
    """
    Analyzer가 선택한 종목.

    거래를 의미하지 않는다.
    특정 날짜에 Analyzer가 해당 종목을 추천했다는 사실만 표현한다.
    """

    analysis: AnalysisResult

    selected_date: datetime

    rank: int

    @property
    def code(self) -> str:
        return self.analysis.code

    @property
    def name(self) -> str:
        return self.analysis.name