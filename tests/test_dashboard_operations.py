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
        self.assertIn(
            '<article class="card full"><h2>매수 선정 종목</h2>',
            self.template,
        )
        self.assertIn(
            '<article class="card full"><h2>관찰 종목</h2>',
            self.template,
        )
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
        self.assertIn('<span class="runner-break" aria-hidden="true"></span><label>대상 월', self.template)
        self.assertNotIn("result.entry_snapshot_saved", self.template)
        self.assertIn("/api/status", self.template)
        self.assertIn("진행률: ${status.progress}%", self.template)
        self.assertIn('id="server-task-status"', self.template)
        self.assertNotIn('id="s80-shadow-trades"', self.template)
        self.assertNotIn('id="s80-entry-layers-report"', self.template)
        self.assertNotIn('id="intraday-exit-coverage-report"', self.template)
        self.assertNotIn('id="s80-exit-bounds-report"', self.template)
        self.assertNotIn('id="s80-no-progress-report"', self.template)
        self.assertNotIn("D.strategy_research", self.template)
        self.assertNotIn("D.operational_shadow", self.template)
        self.assertNotIn("D.observation_shadow", self.template)
        self.assertIn("시가 갭", self.template)
        self.assertIn("진입 조건 충족", self.template)
        self.assertIn("가정 진입일", self.template)
        self.assertIn("가정 진입 시가", self.template)
        self.assertIn("시가 기준 예상 수익률", self.template)
        self.assertIn("Number(p.close)/openPrice-1", self.template)
        self.assertIn("function entryDateLabel(value)", self.template)
        self.assertIn("D.selection_entry_prices", self.template)
        self.assertIn("function applyStoredEntryPrices(items)", self.template)
        self.assertIn("titan-operational-prices", self.template)
        self.assertIn("validCachedOperationalPrices", self.template)
        self.assertIn("window.__operationalPrices=operationalPrices", self.template)
        self.assertIn("row.children[10].textContent='평가 대기'", self.template)
        self.assertIn("renderHistoricalPeriod(currentHistoricalPeriod())", self.template)
        self.assertIn("function removeMarketRelativeColumn(container)", self.template)
        self.assertIn("row.children[12]?.remove()", self.template)
        self.assertNotIn("매수가 (관찰군 가정)", self.template)
        self.assertNotIn("매도가 (관찰군 가정)", self.template)
        self.assertNotIn("관찰 (가정 거래)", self.template)
        self.assertNotIn('data-tab="research-panel"', self.template)
        self.assertNotIn('data-tab="next-day-panel"', self.template)
        self.assertNotIn('id="next-day-verdict"', self.template)
        self.assertNotIn('id="next-day-forecast"', self.template)
        self.assertNotIn("D.next_day_prediction", self.template)
        self.assertNotIn('id="research-generate"', self.template)
        self.assertNotIn('id="research-run"', self.template)
        self.assertNotIn('id="research-weekly"', self.template)
        self.assertNotIn('id="research-challengers"', self.template)
        self.assertNotIn('id="ac-overview-run"', self.template)
        self.assertNotIn('id="shadow-run"', self.template)
        self.assertNotIn('id="shadow-replay-run"', self.template)
        self.assertNotIn('id="weekday-run"', self.template)
        self.assertNotIn('id="event-g-report"', self.template)
        self.assertNotIn('id="monthly-rs-report"', self.template)
        self.assertNotIn('id="adaptive-momentum-report"', self.template)
        self.assertNotIn("/api/research-shadow-run", self.template)
        self.assertNotIn("async function runAcWeekly()", self.template)
        self.assertNotIn("/api/research-shadow-replay", self.template)
        self.assertNotIn("/api/research-shadow-weekday", self.template)
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

    def test_strategy_comparison_lab_is_separate_from_operations(self) -> None:
        self.assertIn('data-tab="strategy-lab-panel"', self.template)
        self.assertIn('id="strategy-lab-panel"', self.template)
        self.assertIn('id="strategy-lab-results"', self.template)
        self.assertIn('id="strategy-lab-ranks"', self.template)
        self.assertIn("/api/run-strategy-comparison", self.template)
        self.assertIn("D.strategy_comparison", self.template)
        self.assertIn("현재 S80 운영 규칙은 변경하지 않습니다", self.template)
        self.assertIn("상대강도 + 단기 눌림목", self.template)
        self.assertIn("거래량 + 가격 돌파", self.template)
        self.assertIn("추세 필터 + 평균회귀", self.template)
        self.assertIn("Rank 1~5, 6~10, 11~20, 21~50", self.template)
        self.assertIn("검증 전 운영 승격 금지", self.template)

    def test_paper_grid_tab_is_read_only_and_controllable(self) -> None:
        self.assertIn('data-tab="paper-grid-panel"', self.template)
        self.assertIn('id="paper-grid-panel"', self.template)
        self.assertIn("KODEX 코스닥150레버리지", self.template)
        self.assertIn("233740", self.template)
        self.assertIn("모의투자 전용", self.template)
        self.assertIn("실제 주문 API는 호출하지 않습니다", self.template)
        self.assertIn("/api/paper-grid", self.template)
        self.assertIn("paperGridAction('start')", self.template)
        self.assertIn("paperGridAction('refresh')", self.template)
        self.assertIn("paperGridAction('stop')", self.template)
        self.assertIn("paperGridAction('reset')", self.template)
        self.assertIn("paperGridState.status!=='STOPPED'", self.template)
        self.assertIn("paperGridUpdateMessage(result.state)", self.template)
        self.assertIn("state.updated_at", self.template)
        self.assertIn('aria-live="polite"', self.template)
        self.assertIn("총수익률", self.template)
        self.assertIn("비용 후 세전 수익률", self.template)
        self.assertIn("x.net_return_before_tax", self.template)
        self.assertIn("<th>매수가</th><th>매도가</th>", self.template)
        self.assertIn("x.buy_price", self.template)
        self.assertIn("x.sell_price", self.template)
        self.assertIn("최대 보유 500주", self.template)
        self.assertIn("100주 × 최대 5단계", self.template)
        self.assertIn("개별 목표가 매도", self.template)
        self.assertIn("급락 시 매수 중단", self.template)

    def test_kiwoom_paper_tab_is_read_only_and_fail_closed(self) -> None:
        self.assertIn('data-tab="kiwoom-paper-panel"', self.template)
        self.assertIn('id="kiwoom-paper-panel"', self.template)
        self.assertIn("V1.3-S80-N7-TP5-SL10-CANDIDATE", self.template)
        self.assertIn("PAPER · MOCK 전용", self.template)
        self.assertIn("이 화면은 상태 조회 전용", self.template)
        self.assertIn("/api/kiwoom-paper/status", self.template)
        self.assertIn("/api/kiwoom-paper/sync", self.template)
        self.assertIn('id="kiwoom-paper-candidates"', self.template)
        self.assertIn('id="kiwoom-paper-positions"', self.template)
        self.assertIn('id="kiwoom-paper-orders"', self.template)
        self.assertIn("safety.new_orders_allowed===true", self.template)
        self.assertNotIn("/api/kiwoom-paper/order", self.template)

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
        self.assertNotIn("historyCohort.value='SELECTED'", self.template)
        self.assertIn("entry_mode:'OPEN'", self.template)
        self.assertNotIn('id="history-entry-mode"', self.template)
        self.assertNotIn('id="history-entry-minimum"', self.template)
        self.assertNotIn('id="history-entry-limit"', self.template)
        self.assertNotIn("historyEntryMode.value='KIS_1000_LIMIT'", self.template)
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
        self.assertIn("const entryMatch=x=>(x.entry_mode||'OPEN')==='OPEN'", self.template)

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
        self.assertNotIn("snapshot = _save_operational_entry_snapshot(prices)", server)
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
