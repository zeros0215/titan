import unittest
from unittest.mock import patch

from broker.factory import ProviderFactory
from config.settings import Settings
from core.container import Container
from domain.enums import MarketType
from runner.factory import create_titan_runner
from runner.titan_runner import TitanRunner


class RunnerFactoryTest(unittest.TestCase):
    def test_builds_a_v1_runner(self) -> None:
        self.assertIsInstance(create_titan_runner(), TitanRunner)

    def test_container_exposes_the_v1_runner(self) -> None:
        self.assertIsInstance(Container().runner, TitanRunner)

    def test_mock_configuration_can_analyze_one_stock(self) -> None:
        mock_settings = Settings(
            env="TEST",
            market_provider="MOCK",
            mock_scenario="BREAKOUT",
            log_level="INFO",
            kis_app_key="",
            kis_app_secret="",
            kis_base_url="",
            kis_account="",
            kis_mode="VIRTUAL",
        )
        with patch("broker.factory.settings", mock_settings):
            runner = create_titan_runner()
        stock = runner.stock_repository.get_all()[0]

        analyses = runner.scanner.scan([stock])

        self.assertIsInstance(stock.market, MarketType)
        self.assertEqual(len(analyses), 1)
        self.assertEqual(analyses[0].code, stock.code)

    def test_kis_configuration_reports_missing_required_settings(self) -> None:
        kis_settings = Settings(
            env="TEST",
            market_provider="KIS",
            mock_scenario="BREAKOUT",
            log_level="INFO",
            kis_app_key="",
            kis_app_secret="",
            kis_base_url="",
            kis_account="",
            kis_mode="VIRTUAL",
        )
        with patch("broker.factory.settings", kis_settings):
            with self.assertRaisesRegex(ValueError, "KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE_URL"):
                ProviderFactory.create()


if __name__ == "__main__":
    unittest.main()
