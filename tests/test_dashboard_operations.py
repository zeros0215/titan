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
        self.assertIn(
            'data-archived-feature="event-candidates" style="display:none"',
            self.template,
        )
        self.assertIn(
            'data-archived-feature="event-performance" style="display:none"',
            self.template,
        )
        self.assertIn("eventShadow.entry_candidates", self.template)
        self.assertIn("9시 50분~10시 10분", self.template)
        self.assertIn('id="news-panel"', self.template)
        self.assertIn("기사 본문이나 자동 매수 판단 없이", self.template)
        self.assertIn("setInterval(refreshOperationalPrices,60000)", self.template)
        self.assertIn('id="breadth-up-rate"', self.template)
        self.assertIn("result.entry_snapshot_saved", self.template)
        self.assertIn("/api/status", self.template)
        self.assertIn('id="server-task-status"', self.template)
        self.assertIn('id="s80-shadow-trades"', self.template)
        self.assertIn('id="s80-entry-layers-report"', self.template)
        self.assertIn("research.s80_entry_layers_report", self.template)
        self.assertIn("D.operational_shadow", self.template)
        self.assertIn("D.observation_shadow", self.template)
        self.assertIn("가정 진입시각", self.template)
        self.assertIn("가정 수익률", self.template)
        self.assertIn('data-tab="research-panel"', self.template)
        self.assertNotIn('data-tab="next-day-panel"', self.template)
        self.assertNotIn('id="next-day-verdict"', self.template)
        self.assertNotIn('id="next-day-forecast"', self.template)
        self.assertNotIn("D.next_day_prediction", self.template)
        self.assertNotIn('id="research-generate"', self.template)
        self.assertNotIn('id="research-run"', self.template)
        self.assertNotIn('id="research-weekly"', self.template)
        self.assertNotIn('id="research-challengers"', self.template)
        self.assertIn('id="challenger-robustness"', self.template)
        self.assertIn('id="challenger-stress"', self.template)
        self.assertIn('id="shadow-replay-month"', self.template)
        self.assertIn('id="shadow-replay-run"', self.template)
        self.assertIn('id="weekday-run"', self.template)
        self.assertIn('id="weekday-results"', self.template)
        self.assertNotIn('id="event-g-report"', self.template)
        self.assertNotIn('id="monthly-rs-report"', self.template)
        self.assertNotIn('id="adaptive-momentum-report"', self.template)
        self.assertIn("/api/research-shadow-run", self.template)
        self.assertIn("async function runAcWeekly()", self.template)
        self.assertIn("acRunButtons.forEach(button=>button.addEventListener('click',runAcWeekly))", self.template)
        self.assertIn("대시보드 서버로 열어야 실행할 수 있습니다", self.template)
        self.assertIn("/api/research-shadow-replay", self.template)
        self.assertIn("/api/research-shadow-weekday", self.template)
        self.assertLess(
            self.template.index("const pct="),
            self.template.index("pct(breadth.up_rate)"),
        )
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

    def test_historical_strategy_selector_keeps_only_useful_comparisons(self) -> None:
        self.assertIn(
            '<option value="V1.3-S80-N7-TP5-SL10-CANDIDATE">',
            self.template,
        )
        self.assertIn(
            '<option value="V1.3-RISK-5D-CANDIDATE">',
            self.template,
        )
        self.assertIn('<option value="V1.1">', self.template)
        self.assertNotIn('<option value="V1.2-CANDIDATE">', self.template)
        self.assertNotIn('<option value="V1.2-GAP-CANDIDATE">', self.template)
        self.assertNotIn('<option value="V1.2-5D-CANDIDATE">', self.template)
        self.assertNotIn(
            '<option value="V1.3-S78-N7-TP5-SL10-CANDIDATE">',
            self.template,
        )
        self.assertIn("function applyHistoryStrategyPreset()", self.template)
        self.assertIn(
            "historyStrategy.value==='V1.3-RISK-5D-CANDIDATE'",
            self.template,
        )
        self.assertIn("historyHolding.value='5'", self.template)
        self.assertIn("historyEntryMode.value='OPEN'", self.template)

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
        self.assertIn('"/api/research-generate"', server)
        self.assertIn('"/api/research-rank"', server)
        self.assertIn('"/api/research-run"', server)
        self.assertIn('"/api/research-run-challengers"', server)
        self.assertIn('"/api/research-shadow-run"', server)
        self.assertIn('"/api/research-shadow-replay"', server)
        self.assertIn('"/api/research-shadow-weekday"', server)
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
