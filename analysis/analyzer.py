"""
TITAN Analyzer Engine
"""


from domain.stock import Stock

from domain.candle_series import CandleSeries

from indicators.calculator import IndicatorCalculator

from scoring.engine import ScoreEngine

from analysis.result import AnalysisResult

from analysis.explainer import AnalysisExplainer

from analysis.recommendation import RecommendationEngine



class Analyzer:


    def __init__(
        self,
        indicator_calculator: IndicatorCalculator,
        score_engine: ScoreEngine
    ):


        self.indicator_calculator = (
            indicator_calculator
        )


        self.score_engine = (
            score_engine
        )


        self.explainer = (
            AnalysisExplainer()
        )


        self.recommendation_engine = (
            RecommendationEngine()
        )



    def analyze(
        self,
        stock: Stock,
        series: CandleSeries
    ) -> AnalysisResult:


        indicators = (
            self.indicator_calculator.calculate(
                series
            )
        )


        score = (
            self.score_engine.calculate(
                indicators
            )
        )


        positive, negative = (
            self.explainer.explain(
                indicators,
                score
            )
        )


        recommendation = (
            self.recommendation_engine.decide(
                score,
                indicators
            )
        )


        return AnalysisResult(

            stock=stock,

            indicators=indicators,

            score=score,

            recommendation=recommendation,

            positive_factors=positive,

            negative_factors=negative

        )