"""
Market Provider Factory
"""

from config.settings import settings

from broker.mock.market import MockMarketProvider


class ProviderFactory:

    @staticmethod
    def create():

        provider = settings.market_provider.upper()

        if provider == "MOCK":
            return MockMarketProvider()

        raise ValueError(
            f"Unsupported provider: {provider}"
        )