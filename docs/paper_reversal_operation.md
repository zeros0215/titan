# 233740 고정 전략 모의 관찰

2026-09-08 장 마감 후 서버를 준비했다. 오늘 장중 실시간 모의 기록은 없으며, 당일 분봉 재생은 output/paper_grid/frozen_validation_20260908/report.md에 별도 기록한다.

실행: `python -m tools.paper_reversal_server`

화면: http://127.0.0.1:8766

상태: http://127.0.0.1:8766/state

출력: output/paper_reversal_live/state.json 및 날짜별 minutes.json, quotes.jsonl, raw_*.json. 실제 주문 없이 조회 시세로 가상 체결한다. 평일 장중 관찰하며 PC와 서버 프로세스가 실행 중이어야 한다. 재부팅 자동 시작은 설정하지 않았다.

고정 조건은 research/paper_reversal.py의 RULES에 있다. 100주 단일 보유, 목표 +50원, 손절 -80원, 수수료 각 0.015%, 체결 불이익 각 5원. 누락·이상 분봉으로는 진입하지 않는다. 과거 신호의 늦은 매수를 제한하며 이전 날짜 포지션은 검토 상태로 남긴다. 화면에서 신규 진입을 일시중지해도 기존 보유 청산 감시는 계속한다.

검증: `python -m unittest tests.test_paper_reversal tests.test_search_233740_mixed tests.test_search_233740_patterns tests.test_search_233740_replay tests.test_compare_233740_timeframes` — 17개 통과.

다음 확인: 장중 heartbeat 갱신, DATA_ERROR 및 INVALID_PRICE 빈도, 원본 시세 품질, 실제로 기록된 모의 거래와 비용 후 손익. 규칙 변경 없이 관찰 표본을 축적한다.
