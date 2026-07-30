# TITAN V1.0

TITAN은 시장 상황(Context)과 종목 특성(Feature)을 함께 분석해 향후 상승 가능성이 높은 종목을 **선정하고 사후 검증**하는 플랫폼입니다.

자동 주문, 포트폴리오 관리, 브로커 거래 기능은 V1 범위에 포함하지 않습니다.

## V1 workflow

```text
Market Data → Analysis → Ranking → Selection → Backtest → Validation → Report
```

1. `select`는 특정 시점까지의 가격 데이터만 사용해 후보를 분석·선정하고, 선정 근거와 당시 가격 데이터를 보관합니다.
2. 시간이 지난 뒤 `validate`는 저장된 선정 결과와 이후 가격을 사용해 수익률을 재현하고 검증합니다.
3. `report`는 저장된 모든 검증 결과를 누적 집계합니다.

선정 시점 이후의 캔들은 분석에 사용하지 않습니다. 이를 통해 미래 데이터가 분석에 섞이는 것을 방지합니다.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

기본값은 `MARKET_PROVIDER=MOCK`이며 기본 MOCK 시나리오는 강한 후보를 만들어 전체 흐름을 확인하기 위한 `BREAKOUT`입니다. MOCK은 같은 기준일·종목·시나리오에서 같은 OHLCV를 만들어 로컬 V1 흐름을 재현할 수 있습니다. 필요하면 `MOCK_SCENARIO=BULL`처럼 `bull`, `bear`, `sideways`, `breakout`, `crash` 중 하나를 설정할 수 있습니다. 실제 KIS 시세를 사용하려면 프로젝트 루트에 `.env` 파일을 만들고 다음 값을 설정합니다.

```dotenv
MARKET_PROVIDER=KIS
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_BASE_URL=your_kis_environment_base_url
```

모의투자/실전투자 환경에 맞는 KIS 앱 키와 base URL을 사용해야 합니다. 비밀 값이 담긴 `.env`는 저장소에 포함하지 않습니다.

## Commands

선정 전에 설정과 종목 유니버스를 확인합니다. 이 명령은 네트워크 시세를 요청하지 않습니다.

```powershell
python -m app.main check
```

선정일 기준 후보를 최대 5개 선정합니다.

```powershell
python -m app.main select --date 2026-07-27 --top-n 5
```

선정 보고서에는 순위, 점수, 예측·판단 등급, 활성 특성 및 시장 Context가 표시됩니다.

평가일이 지난 선정 결과를 검증합니다. 아래 예시는 3% 이상 수익을 성공으로 정의합니다.

```powershell
python -m app.main validate `
  --selection-date 2026-07-27 `
  --evaluation-date 2026-08-17 `
  --holding-days 20 `
  --success-return 0.03
```

`evaluation-date`는 `selection-date`보다 뒤여야 하며, `holding-days`는 양수여야 합니다. 해당 선정일의 스냅샷이 없으면 검증은 실행되지 않습니다.

모든 검증 이력의 누적 성과를 확인합니다.

```powershell
python -m app.main report
```

## Stored outputs

- `output/selections/`: 일자별 선정 스냅샷과 점수·특성·판단 근거
- `output/market_data/`: 선정 당시의 캔들 데이터 캐시
- `output/validations/`: 검증 결과와 누적 보고용 이력
- `output/reports/`: 선정·개별 검증·누적 검증 Markdown 보고서

동일한 선정일·평가일로 다시 검증하면 해당 검증 파일은 최신 결과로 갱신됩니다.

## Selection criteria

V1 점수 예산은 총 100점입니다. 활성화된 Feature는 해당 조건의 배점을 받고, Feature 강도와 원본 지표 값은 과열 필터 및 선정 근거로 별도 보존합니다.

| Category | Maximum score |
|---|---:|
| Trend | 30 |
| Momentum | 15 |
| Volume | 15 |
| Price action | 15 |
| Risk | 15 |
| Market context | 10 |

후보는 기본적으로 총점 80점 이상이며, 추세·위험·시장 강도·과열 모멘텀 조건을 모두 통과해야 합니다. 기준값은 `config/selection_criteria.py`에 모여 있으므로 전략 조정 시 엔진 코드의 수정 범위를 최소화할 수 있습니다.

70% 승률은 검증을 통해 추적할 목표이지, 점수 기준만으로 보장되는 값은 아닙니다. 누적 `report`의 표본 수, 승률, 평균 수익률을 함께 확인해 기준을 조정합니다.

## V1 boundaries

V1은 종목 선정 품질을 검증하는 데 집중합니다. 아래 항목은 이후 버전 범위입니다.

- Portfolio, Position, Trade, Order, Broker execution
- Paper/Live trading
- Risk/Money management
- Feature auto-learning, model retraining, hyperparameter search
