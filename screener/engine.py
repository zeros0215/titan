"""
TITAN Screener
"""

from features.engine import FeatureEngine

from factors.engine import FactorEngine

from strategy.titan_strategy import TitanStrategy

from ranking.ranking_item import RankingItem

from screener.ranking import Ranking


class ScreenerEngine:

    def __init__(self):

        self.feature_engine = FeatureEngine()

        self.factor_engine = FactorEngine()

        self.strategy = TitanStrategy()

    def run(

        self,

        histories

    ) -> list[RankingItem]:

        ranking = []

        for history in histories:

            feature = self.feature_engine.calculate(history)

            factor = self.factor_engine.calculate(feature)

            strategy = self.strategy.evaluate(factor)

            ranking.append(

                RankingItem(

                    stock=history.stock,

                    feature=feature,

                    factor=factor,

                    strategy=strategy

                )

            )

        return Ranking.sort(ranking)