import unittest
from pathlib import Path


class DashboardTabRestoreTest(unittest.TestCase):
    def test_reload_persists_the_visibly_active_tab_in_the_url(self) -> None:
        template = (
            Path(__file__).resolve().parent.parent
            / "dashboard"
            / "index.template.html"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "document.querySelector('.tab-button.active')?.dataset.tab",
            template,
        )
        self.assertIn("url.searchParams.set('tab',activeTab)", template)
        self.assertIn("url.searchParams.set('tab',button.dataset.tab)", template)


if __name__ == "__main__":
    unittest.main()
