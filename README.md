# TITAN

TITAN은 한국 주식 시장의 Context와 종목 Feature를 함께 분석해 후보를 선정하고,
선정 당시의 근거를 보존한 뒤 시간순으로 성과를 검증하는 연구·운영 관찰 플랫폼이다.

현재 범위는 **조회, 선정, 백테스트, 모니터링, 모의 관찰**까지다. KIS 연동은
읽기 전용이며 실제 주문 API를 호출하지 않는다. 대시보드에서 사용하는
`V1.3-S80-N7-TP5-SL10-CANDIDATE`도 승인된 실거래 전략이 아니라 관찰 중인 후보 전략이다.

## 구현 범위

```text
시장/KIS 데이터
  -> 데이터 품질 및 시점별 유니버스 검사
  -> Context + Feature 분석과 종목 선정
  -> 선정 스냅샷 및 관찰 코호트 저장
  -> 5·10·20·40 거래일 검증
  -> Walk-forward 및 전략 비교
  -> KPI 모니터링과 변경 승인 게이트
  -> 로컬 대시보드 및 주문 없는 모의 관찰
```

- MOCK, 과거 파일 및 KIS 읽기 전용 시장 데이터 공급자
- 추세·모멘텀·거래량·가격 행동·위험·시장 Context 기반 점수화
- 거래비용과 슬리피지를 반영한 검증 및 벤치마크 비교
- 수정주가와 point-in-time 유니버스의 스테이징·검증·승격
- 전략 설정 해시, Walk-forward 근거 및 사람 승인을 요구하는 변경 게이트
- 일일 실행 중복 방지, 부분 실패 격리, KPI `NORMAL/WATCH/ALERT` 판정
- S80 선정, 전략 연구 및 233740 모의 관찰을 제공하는 로컬 대시보드

## 중요한 현재 상태

- 실제 주문, 실계좌 포지션 및 자금 관리는 구현하지 않는다.
- 현재 로컬 활성 유니버스 매니페스트는 대상 기간의 point-in-time 완전성을
  선언하지만, 전체 활성 데이터는 `PROVISIONAL`이다. KRX 가격 원천에 공식
  수정주가 필드가 없어 기업행위와 품질 격리 구간의 검토 전에는 정식 전략
  승격이 차단된다.
- 페이퍼 전략 결과는 연구 표본이며 수익을 보장하지 않는다.
- 운영 설정과 비밀값은 `.env`에 두며 저장소에 커밋하지 않는다.

## 설치

Python 3.12를 기준으로 개발한다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

기본 설정은 MOCK 데이터다. `.env.example`을 참고해 프로젝트 루트에 `.env`를
만들 수 있다. KIS를 사용할 때만 읽기 전용 자격 증명을 설정한다.

```dotenv
MARKET_PROVIDER=KIS
KIS_MODE=VIRTUAL
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_BASE_URL=your_kis_environment_base_url
KIS_ACCOUNT=your_account
```

## 빠른 시작

```powershell
python -m app.main check
python -m app.main select --date 2026-09-29 --top-n 5
python -m app.main daily --date 2026-09-29
python -m app.main report
python -m app.main monitor
python -m app.main --help
```

## 테스트

```powershell
python -m pytest
```

테스트 설정은 저장소 루트를 import 경로에 포함하고 `tests/`만 수집한다.
KIS 자격 증명이나 네트워크가 필요한 실제 연동 점검은 일반 테스트와 분리한다.

## 데이터와 산출물

- `resources/`: 기본 종목군과 입력 템플릿
- `output/selections/`: 날짜별 선정과 판단 근거
- `output/validations/`: 보유기간별 검증 결과
- `output/walk_forward/`: 시간순 백테스트와 아티팩트
- `output/monitoring/`: KPI 상태 스냅샷
- `output/reports/`: 사람이 읽는 운영·검증 보고서
- `output/kis_pilot/`: 실행별로 격리된 KIS 읽기 전용 파일럿
- `output/paper_grid/`, `output/paper_reversal_live/`: 실제 주문 없는 모의 상태

`output/`, `logs/`, 로컬 캐시와 비밀값은 버전 관리 대상이 아니다. 장기 운영
환경에서는 원시 데이터와 감사 근거를 별도 보관 정책에 따라 백업해야 한다.

## 운영 및 연구 문서

- [일일 운영](docs/daily_operation.md)
- [KPI 모니터링](docs/kpi_monitoring.md)
- [KIS 읽기 전용 파일럿](docs/kis_pilot.md)
- [전략 연구](docs/strategy_research.md)
- [전략 변경 게이트](docs/strategy_change_gate.md)
- [V1 백테스트 릴리스](docs/v1_backtest_release.md)
- [과거 시점별 유니버스 적재](docs/point_in_time_universe_ingestion.md)
- [정식 승격 준비 상태](docs/release_readiness.md)
- [실매매 준비 아키텍처](docs/live_trading_architecture.md)
- [233740 고정 전략 모의 관찰](docs/paper_reversal_operation.md)

## 정식 전략 승격 전 필수 조건

1. 공식 원천으로 과거 신규상장·상장폐지·시장 이전을 포함한 유니버스의
   `COMPLETE` 판정을 재검토하고 원본 해시를 보존한다.
2. 수정주가, 거래비용 및 슬리피지 근거를 고정한다.
3. 동일 조건의 기준/후보 Walk-forward와 재현성 검사를 통과한다.
4. 충분한 KIS 파일럿 및 forward-paper 표본을 검토한다.
5. 전략 변경 게이트를 통과한 후보를 사람이 명시적으로 승인한다.
