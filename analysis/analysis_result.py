from dataclasses import dataclass, field
from typing import Optional

from feature.feature_set import FeatureSet
from indicators.bundle import IndicatorBundle
from prediction.prediction_result import PredictionResult
from scoring.score_result import ScoreResult
from decision.decision_result import DecisionResult
from domain.enums import MarketType
from market.context.market_context import MarketContext

@dataclass(slots=True)
class AnalysisResult:
    """
    종목 분석 결과

    Analyzer에서 생성되는 최종 분석 결과 객체이다.
    """

    code: str

    name: str

    indicators: IndicatorBundle

    features: FeatureSet

    score: ScoreResult

    prediction: Optional[PredictionResult] = None

    decision: Optional[DecisionResult] = None

    positive_factors: list[str] = field(default_factory=list)

    negative_factors: list[str] = field(default_factory=list)

    market: MarketType | None = None

    context: MarketContext | None = None
