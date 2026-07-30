from report.report_result import ReportResult

from ranking.ranking_item import RankingItem


class ReportBuilder:
    """
    Ranking 결과를 Report로 변환
    """

    def build(
        self,
        item: RankingItem,
    ) -> ReportResult:

        analysis = item.analysis

        return ReportResult(
            rank=item.rank,

            code=analysis.code,
            name=analysis.name,

            score=analysis.score.total_score,

            prediction=analysis.prediction.grade.value,
            decision=analysis.decision.decision.value,

            confidence=analysis.prediction.confidence,
            expected_return=analysis.prediction.expected_return,

            positive_factors=analysis.positive_factors,
            negative_factors=analysis.negative_factors,
        )