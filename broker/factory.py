"""
Market Provider Factory
"""

from config.settings import settings

from broker.mock.market import MockMarketProvider
from broker.mock.scenario import MarketScenario

from broker.kis.market import KisMarketProvider


class ProviderFactory:


    @staticmethod
    def create():

        provider = settings.market_provider.upper()


        if provider == "MOCK":

            return ProviderFactory._create_mock()


        if provider == "KIS":

            return ProviderFactory._create_kis()


        raise ValueError(
            f"Unknown market provider: {provider}"
        )


    @staticmethod
    def _create_mock():

        return MockMarketProvider(
            scenario=MarketScenario.BULL
        )


    @staticmethod
    def _create_kis():

        return KisMarketProvider()