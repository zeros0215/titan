import unittest
from pathlib import Path


class DashboardOperationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = (
            Path(__file__).resolve().parent.parent
            / "dashboard"
            / "index.template.html"
        ).read_text(encoding="utf-8")

    def test_current_view_has_action_and_position_sections(self) -> None:
        self.assertIn('id="today-action"', self.template)
        self.assertIn('id="operational-selection-run"', self.template)
        self.assertIn('id="operational-selection-date"', self.template)
        self.assertIn("/api/run-operational-selection", self.template)
        self.assertIn(
            "JSON.stringify({date:operationalSelectionDate.value})",
            self.template,
        )
        self.assertIn(
            "sessionStorage.setItem('titan-operational-view-date',result.date)",
            self.template,
        )
        self.assertIn(
            "operationalRuns.filter(x=>x.as_of&&x.as_of.slice(0,10)===operationalViewDate)",
            self.template,
        )
        self.assertIn('id="positions"', self.template)
        self.assertIn("/api/current-prices", self.template)
        self.assertIn("/api/news-headlines", self.template)
        self.assertIn("/api/run-event-candidates", self.template)
        self.assertIn('id="event-candidate-run"', self.template)
        self.assertIn('id="event-candidates"', self.template)
        self.assertIn('id="event-shadow-trades"', self.template)
        self.assertIn("eventShadow.entry_candidates", self.template)
        self.assertIn("9시 50분~10시 10분", self.template)
        self.assertIn('id="news-panel"', self.template)
        self.assertIn("기사 본문이나 자동 매수 판단 없이", self.template)
        self.assertIn("setInterval(refreshOperationalPrices,60000)", self.template)
        self.assertIn("<th>선정일 대비</th>", self.template)
        self.assertNotIn("<th>보조지표</th>", self.template)
        self.assertIn(
            "Number(p.close)/Number(selectionClose)-1",
            self.template,
        )
        self.assertIn(
            '<article class="card hero" style="display:none">',
            self.template,
        )
        self.assertIn("localSelection?'로컬 KRX':pct(L.api_success_rate)", self.template)
        self.assertIn("titan-positions", self.template)
        self.assertIn("익절 확인", self.template)
        self.assertIn("손절 확인", self.template)

    def test_current_history_uses_only_operational_runs(self) -> None:
        self.assertIn("const operationalRunByDate=new Map()", self.template)
        self.assertIn(
            "const operationalRuns=[...operationalRunByDate.values()]",
            self.template,
        )
        self.assertIn("아직 S80 공식 실행 기록이 없습니다", self.template)

    def test_historical_cohort_selector_controls_all_tables(self) -> None:
        self.assertIn(
            "const visibleCohorts=historyCohort.value==='COMPARE'",
            self.template,
        )
        self.assertIn(
            ":[historyCohort.value]",
            self.template,
        )
        self.assertNotIn(
            "if(historyEntryMode.value==='KIS_1000_LIMIT')historyCohort.value='SELECTED'",
            self.template,
        )
        local_test = (
            Path(__file__).resolve().parent.parent
            / "tools"
            / "local_monthly_test.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('if cohort != "SELECTED"', local_test)
        self.assertIn(
            "return sessionStorage.getItem('titan-history-result-period')||historyMonth.value||historyYear.value",
            self.template,
        )
        self.assertNotIn(
            "return pageParams.get('month')||pageParams.get('year')||sessionStorage.getItem('titan-history-result-period')",
            self.template,
        )

    def test_historical_trades_are_deduplicated_by_identity(self) -> None:
        self.assertIn("const tradeByIdentity=new Map()", self.template)
        self.assertIn(
            "`${cohortOf(x)}|${x.selection_date}|${x.code}`",
            self.template,
        )

    def test_server_exposes_operational_selection_endpoint(self) -> None:
        server = (
            Path(__file__).resolve().parent.parent
            / "tools"
            / "kis_dashboard_server.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"/api/run-operational-selection"', server)
        self.assertIn('"/api/news-headlines"', server)
        self.assertIn('"/api/run-event-candidates"', server)
        self.assertIn("def _run_event_candidates", server)
        self.assertIn("def _find_cached_operational_selection", server)
        self.assertIn('"cached": True', server)
        self.assertIn("def _news_headlines", server)
        self.assertIn('"--top-n", "7"', server)
        self.assertIn('"--prefer-local-history"', server)
        self.assertIn(
            '"V1.3-S80-N7-TP5-SL10-CANDIDATE"',
            server,
        )


if __name__ == "__main__":
    unittest.main()
