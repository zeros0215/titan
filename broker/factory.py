from config.settings import settings

from broker.mock.market import MockMarketProvider
from broker.mock.scenario import MarketScenario

from broker.kis.market import KisMarketProvider


class ProviderFactory:

    @staticmethod
    def create():

        provider = (

            settings.market_provider

            .upper()

        )

        if provider == "MOCK":
            try:
                scenario = MarketScenario(settings.mock_scenario.lower())
            except ValueError as error:
                choices = ", ".join(item.value for item in MarketScenario)
                raise ValueError(
                    f"Unknown MOCK_SCENARIO: {settings.mock_scenario}. Use one of: {choices}"
                ) from error
            return MockMarketProvider(
                scenario=scenario
            )

        if provider == "KIS":
            ProviderFactory._validate_kis_settings()
            return KisMarketProvider()

        raise ValueError(

            f"Unknown provider : {provider}"

        )

    @staticmethod
    def _validate_kis_settings() -> None:
        required = {
            "KIS_APP_KEY": settings.kis_app_key,
            "KIS_APP_SECRET": settings.kis_app_secret,
            "KIS_BASE_URL": settings.kis_base_url,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                "KIS market provider requires environment settings: "
                + ", ".join(missing)
            )

        if not settings.kis_base_url.startswith(("https://", "http://")):
            raise ValueError("KIS_BASE_URL must start with http:// or https://")
