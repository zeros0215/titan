"""
TITAN Analyzer Engine
"""

from typing import Optional

from analysis.analysis_result import AnalysisResult

from domain.stock import Stock
from domain.candle_series import CandleSeries

from feature.feature_engine import FeatureEngine
from feature.feature_set import FeatureSet

from indicators.bundle import IndicatorBundle
from indicators.calculator import IndicatorCalculator

from market.context.market_context import MarketContext

from scoring.score_engine import ScoreEngine
from scoring.score_result import ScoreResult

from prediction.prediction_engine import PredictionEngine
from prediction.prediction_result import PredictionResult

from decision.decision_engine import DecisionEngine
from decision.decision_result import DecisionResult


class Analyzer:
    """
    TITAN 분석 파이프라인

    Stock
        ↓
    CandleSeries
        ↓
    Indicator 계산
        ↓
    Feature 추출
        ↓
    Score 계산
        ↓
    Prediction
        ↓
    Decision
        ↓
    AnalysisResult 생성
    """

    def __init__(
        self,
        indicator_calculator: IndicatorCalculator,
        feature_engine: FeatureEngine,
        score_engine: ScoreEngine,
        prediction_engine: PredictionEngine,
        decision_engine: DecisionEngine,
    ) -> None:

        self.indicator_calculator: IndicatorCalculator = indicator_calculator
        self.feature_engine: FeatureEngine = feature_engine
        self.score_engine: ScoreEngine = score_engine

        self.prediction_engine: PredictionEngine = prediction_engine
        self.decision_engine: DecisionEngine = decision_engine

    def analyze(
        self,
        stock: Stock,
        series: CandleSeries,
        context: Optional[MarketContext] = None,
    ) -> AnalysisResult:

        #
        # Indicator
        #

        indicators: IndicatorBundle = (
            self.indicator_calculator.calculate(series)
        )

        #
        # Feature
        #

        features: FeatureSet = (
            self.feature_engine.extract(
                series,
                indicators,
            )
        )

        #
        # Score
        #

        score: ScoreResult = (
            self.score_engine.calculate(
                features,
                context,
            )
        )

        #
        # Prediction
        #

        prediction: PredictionResult = (
            self.prediction_engine.predict(score)
        )

        #
        # Decision
        #

        decision: DecisionResult = (
            self.decision_engine.decide(prediction)
        )

        #
        # Explanation
        #

        positive: list[str] = [
            feature.reason
            for feature in features.enabled()
            if feature.reason
        ]

        negative: list[str] = [
            feature.reason
            for feature in features.disabled()
            if feature.reason
        ]

        #
        # Result
        #

        return AnalysisResult(
            code=stock.code,
            name=stock.name,
            indicators=indicators,
            features=features,
            score=score,
            prediction=prediction,
            decision=decision,
            positive_factors=positive,
            negative_factors=negative,
            market=stock.market,
            context=context,
        )
