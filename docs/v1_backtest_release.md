# TITAN V1 백테스트 릴리스 절차

TITAN의 목표는 시장 상황(Context)과 종목 특성(Feature)을 함께 분석하여
향후 상승 가능성이 높은 종목을 지속적으로 선별하고 검증하는 것이다.

## 1. 전략 동결

```powershell
python -m app.main v1-release-check
```

코드에서 선정 기준, 점수 가중치, 시점별 Top 500 유니버스, 다음 거래일
시가 진입, 20거래일 종가 청산 및 거래비용을 추출해
`output/release/v1.0.0/strategy_spec.json`에 저장한다. 전체 테스트,
preflight, 2023~2025 Walk-forward와 재현성 검사를 수행한 뒤 모든 근거를
같은 릴리스 디렉터리에 해시와 함께 패키징한다.

## 2. 사전검증

외부에서 확보한 수정주가 CSV는 먼저 스테이징으로 컴파일한다.

```powershell
python -m app.main price-history-compile `
  --input data/prices.csv `
  --source-manifest data/price_source.json `
  --coverage-start 2022-01-03 `
  --coverage-end 2025-12-30 `
  --output-dir output/price_history_staging
```

입력 형식은 `resources/price_history/history_template.csv`, 출처 정보는
`resources/price_history/source_manifest_template.json`을 사용한다. 모든 행은
수정주가임을 나타내는 `adjusted=true`가 필요하다. 컴파일 결과는 원본 SHA-256과
출처 정보를 포함하며 활성 데이터 디렉터리를 직접 덮어쓰지 않는다.

```powershell
python -m app.main backtest-preflight
```

다음 조건을 모두 통과해야 정식 백테스트를 실행한다.

- 동결 사양의 SHA-256 일치
- 당시 시점 기준 종목군(point-in-time universe) 완성
- 최소 종목 수 충족
- 종목별 가격 데이터 존재
- 최소 3년 가격 이력
- 수정주가 사용 근거
- 거래비용과 슬리피지 가정이 0이 아님

## 3. Walk-forward 백테스트

사전검증이 READY가 된 뒤 아래처럼 실행한다.

```powershell
python -m app.main walk-forward `
  --history-start-year 2022 `
  --first-test-year 2023 `
  --last-test-year 2025 `
  --holding-days 20 `
  --interval-months 1 `
  --top-n 5 `
  --success-return 0.03
```

KIS 5거래일 파일럿은 실운영 연결 안정성 검증이며, 과거 데이터의 생존편향
통제 여부를 확인하는 백테스트 사전검증과 별도로 누적한다.
