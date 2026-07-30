# TITAN KIS 읽기 전용 파일럿

파일럿은 실제 KIS 시세로 Context + Feature 선정 흐름을 검증하지만 주문
API를 포함하지 않는다. 기존 MOCK 아티팩트와 분리된 `output/kis_pilot`에
저장한다.

V1.1 운영 파일럿은 승격된 시점별 시가총액 Top 500 중 거래대금 50억 원
이상이며 관리종목·스팩·우선주가 아닌 종목을 사용한다. 일봉이 확정된
15:40 KST 이후에만 당일 실행을 허용한다.

```powershell
python -m app.main kis-pilot `
  --date 2026-07-29 `
  --top-n 5 `
  --active-data output/release/backtest_data.json `
  --output-dir output/kis_v1_1
```

## 1회 통과 기준

- 종목 조회 실패 0건
- 데이터 품질 제외율 5% 이하
- KIS API 성공률 98% 이상
- 실제 API 시도 대비 재시도율 20% 이하
- 성공률은 재시도 횟수가 아니라 최종 성공·실패 요청을 기준으로 계산
- 주문 요청 0건

각 실행은 다음 위치에 격리 저장한다.

- `output/kis_pilot/selections`
- `output/kis_pilot/observations`
- `output/kis_pilot/quality`
- `output/kis_pilot/universe`
- `output/kis_pilot/market_data`
- `output/kis_pilot/runs`
- `output/kis_pilot/reports`
- `output/kis_pilot/artifacts/<run_id>`

같은 날짜를 다시 실행해도 실행 ID별 아티팩트가 분리되어 이전 스냅샷을
덮어쓰지 않는다. 토큰 발급이 제한되면 동일 프로세스에서는 60초 동안
같은 실패를 재사용해 종목마다 토큰 발급을 반복하지 않는다.

한 번의 통과는 연결 안정성만 의미한다. 운영 파일럿 통과에는 최소 5거래일
연속 실행과 결과 검토가 필요하다. 파일럿이 통과해도 기본 공급자는 자동으로
KIS로 변경되지 않는다.

누적 준비 상태:

```powershell
python -m app.main kis-pilot-report --required-days 5
```

같은 거래일에 여러 번 실행한 경우 가장 나쁜 상태, 가장 낮은 성공률,
가장 높은 재시도율과 제외율을 그날의 대표값으로 사용한다. 반복 실행 중
좋은 결과만 선택해 준비 상태를 높일 수 없다.
