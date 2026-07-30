# TITAN 전략 변경 게이트

전략 변경 게이트는 성과 경고가 발생했을 때 현재 전략이 자동으로 수정되는
것을 막는다. 승인된 후보도 자동 배포되지 않는다.

## 상태

- `PROPOSED`: 후보 설정과 설명이 등록됨
- `PASSED`: 모든 정량·데이터 신뢰성 게이트 통과
- `FAILED`: 하나 이상의 게이트 실패
- `APPROVED`: 통과 후보를 사람이 근거와 함께 승인

후보 설정은 정렬된 JSON의 SHA-256 해시로 고정된다. 저장 후 설정을
변경하면 무결성 검사에서 거부된다. 모든 제안·평가·승인은 행위자와 시각,
근거가 감사 이력에 추가된다.

## 기본 승인 조건

- 기준과 후보의 보유기간 및 검증 간격 동일
- 후보 전략이 Walk-forward 전체에서 고정
- 최소 2개 테스트 폴드와 100개 표본
- 검증 완료율 80% 이상
- Walk-forward 오류 없음
- 모든 폴드의 시점별 유니버스 커버리지 `COMPLETE`
- 거래비용 반영 순수익률이 기준보다 0.5%p 이상 개선
- 벤치마크 초과수익률이 기준보다 0.5%p 이상 개선
- 승률이 하락하지 않음
- 후보 초과수익률이 양수
- 최소 3분의 2 폴드에서 기준 초과수익 개선

현재 과거 유니버스가 `PARTIAL`이므로 정식 승인 조건을 통과할 수 없다.
이는 생존편향 가능성을 숨긴 채 전략을 채택하는 것을 방지하기 위한 차단이다.

## 사용 흐름

후보 설정 등록:

```powershell
python -m app.main strategy-propose `
  --version 1.1.0 `
  --description "변경 목적과 가설" `
  --config candidate.json `
  --actor analyst
```

동일한 Walk-forward 계획으로 생성한 기준·후보 결과 평가:

```powershell
python -m app.main walk-forward `
  --history-start-year 2022 `
  --first-test-year 2023 `
  --last-test-year 2025 `
  --candidate-version 1.1.0

python -m app.main strategy-evaluate `
  --version 1.1.0 `
  --baseline-result baseline-result.json `
  --candidate-result candidate-result.json `
  --actor reviewer
```

후보 Walk-forward는 등록된 설정 해시를 결과에 포함하고
`output/walk_forward/artifacts/<후보버전>` 아래에서 기준 전략과 분리해
실행된다. 현재 지원되는 후보 설정은 `SelectionCriteria`의 선정 임계값이다.

모든 게이트를 통과한 후보만 승인:

```powershell
python -m app.main strategy-approve `
  --version 1.1.0 `
  --actor owner `
  --note "Walk-forward 및 데이터 커버리지 검토 완료"
```

후보와 감사 이력은 `output/strategy_candidates`, 보고서는
`output/reports/strategy_gate_<version>.md`에 저장된다.
