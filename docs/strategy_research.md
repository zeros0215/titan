# TITAN 전략 연구 탐색

운영 중인 `V1.3-S80-N7-TP5-SL10-CANDIDATE`는 변경하지 않고 연구 후보를
생성하고 시간순 워크포워드 결과를 비교한다. 연구 명령은 후보를 승인하거나
운영 전략을 자동 교체하지 않는다.

## 제한된 후보 생성

```powershell
python -m app.main strategy-research-generate
```

기본 탐색 범위는 다음 항목의 81개 조합이다.

- 최소 점수: 78, 80, 82
- 최소 시장 강도: 0.55, 0.60, 0.65
- 5일 모멘텀 상한: 8, 10, 12
- 추세/위험 가중치: 30/15, 35/10, 25/20

약세장 차단, 복합 변동성 경고 제외, 거래량 급증 또는 상승 가속도 요구 등
S80의 안전 필터는 모든 후보에서 유지된다. 설정은
`output/strategy_research/candidates`에 저장된다.

## 후보별 워크포워드

대시보드의 `대표 후보 5개 검증 실행`은 기준형·공격형·방어형·추세강화형·
위험강화형을 2023~2025 시간순 폴드로 실행한다. 계산 중 서버를 종료하지
않아야 하며 환경에 따라 수십 분 걸릴 수 있다.

검토할 설정만 기존 변경 게이트에 등록한 뒤 동일한 기간과 조건으로 실행한다.

```powershell
python -m app.main strategy-propose `
  --version research-s82-m60-mom10 `
  --description "bounded offline research" `
  --config output/strategy_research/candidates/s82-m60-mom10.json `
  --actor analyst

python -m app.main walk-forward `
  --history-start-year 2022 `
  --first-test-year 2023 `
  --last-test-year 2025 `
  --holding-days 20 `
  --candidate-version research-s82-m60-mom10
```

기준 전략과 후보는 반드시 같은 기간, 보유기간, 검증 간격으로 실행한다.

## 결과 순위

```powershell
python -m app.main strategy-research-rank `
  --results-dir output/walk_forward `
  --minimum-trades 100
```

순위는 시장 대비 초과수익을 우선 사용하고, 시간순 검증 폴드의 복리 곡선에서
계산한 최대낙폭과 폴드 간 불안정성·손실 폴드를 패널티로 반영한다. 거래별
자산곡선이 추가되기 전까지 최대낙폭은 폴드 단위의 보수적 연구 지표다.
거래 100건 미만이거나 초과수익이 없는 결과는 승인 가능한
후보로 표시하지 않는다. 순위가 높아도 기존 `strategy-evaluate`와 사람의 승인을
통과하기 전에는 운영 전략으로 사용할 수 없다.
