# TITAN 과거 시점별 유니버스 적재

이 파이프라인은 과거 종목 이력을 검증해 날짜별 KOSPI·KOSDAQ 구성 종목
파일을 생성한다. 원천 데이터가 실제로 완전하다는 증거가 없으면
`COMPLETE`로 표시하지 않는다.

## 이력 CSV

UTF-8 CSV에 다음 열이 필요하다.

```text
code,name,market,effective_from,effective_to,source_id
005930,삼성전자,KOSPI,1975-06-11,,KRX_LISTING_HISTORY
123456,이전종목,KOSDAQ,2010-01-01,2020-06-29,KRX_MARKET_TRANSFER
123456,이전종목,KOSPI,2020-06-30,,KRX_MARKET_TRANSFER
```

- 날짜는 ISO `YYYY-MM-DD`
- `effective_to`는 해당 시장에 포함되는 마지막 날짜
- 현재 상장 중이면 `effective_to`를 비워 둔다.
- 시장 이전은 같은 코드에 대해 겹치지 않는 두 기간으로 기록한다.
- `source_id`는 각 레코드의 출처를 추적할 수 있어야 한다.

## 원천 매니페스트

```json
{
  "source_name": "검증된 원천 이름",
  "source_type": "official_history",
  "dataset_id": "공식 데이터셋 식별자",
  "evidence_url": "https://공식-원천-주소",
  "acquired_at": "2026-07-28T10:00:00+09:00",
  "source_complete": true,
  "coverage_start": "2010-01-01",
  "coverage_end": "2025-12-31"
}
```

`source_complete`는 해당 기간의 신규상장·상장폐지·시장 이전을 모두
포함한다는 확인이 있을 때만 `true`로 설정한다. 요청 커버리지와 원천
커버리지가 정확히 일치하지 않으면 결과는 자동으로 `PARTIAL` 처리된다.
데이터셋 ID, 공식 증거 URL, 취득 시각 중 하나라도 없으면 역시
`COMPLETE`가 될 수 없다.

## 컴파일

```powershell
python -m app.main universe-compile `
  --input history.csv `
  --source-manifest source_manifest.json `
  --coverage-start 2010-01-01 `
  --coverage-end 2025-12-31 `
  --output-dir output/universe_staging
```

활성 `resources/market` 디렉터리에 직접 덮어쓰는 것은 차단된다. 생성된
다음 파일을 검토한 뒤 별도의 승격 절차로 적용해야 한다.

- `kospi.csv`
- `kosdaq.csv`
- `universe_manifest.json`
- `compilation_report.md`

## 검증 규칙

- 코드·이름·시장·시작일·출처 필수
- 종료일이 시작일보다 빠른 기간 차단
- 완전히 동일한 기간 중복 차단
- 같은 종목의 기간 중첩 차단
- 시장 이전 사이의 기간 공백 경고
- 입력 및 생성 파일 SHA-256 기록
- 생성 파일 변조 시 `COMPLETE` 즉시 취소
- 선언된 커버리지 밖의 날짜는 `COMPLETE`로 판정하지 않음

현재 프로젝트에는 완전한 공식 과거 이력 원천이 포함되어 있지 않으므로,
기존 활성 유니버스는 계속 `PARTIAL/UNKNOWN` 상태를 유지한다.

## KRX 공식 Open API 수집

KRX Data Marketplace 회원가입, 인증키 발급, 다음 두 서비스의 활용 승인이
필요하다.

- 유가증권 종목기본정보 `stk_isu_base_info`
- 코스닥 종목기본정보 `ksq_isu_base_info`

인증키는 파일에 저장하지 않고 `KRX_AUTH_KEY` 환경 변수로 전달한다.

```powershell
$env:KRX_AUTH_KEY = "발급받은 키"
python -m app.main krx-universe-collect `
  --start 2010-01-04 `
  --end 2025-12-31 `
  --raw-dir output/krx_universe_raw `
  --max-requests 5000
```

호출 예산에 도달하면 안전하게 종료하며, 같은 명령을 다시 실행하면 이미
저장한 시장·날짜 응답은 건너뛴다. 인증키는 원본이나 매니페스트에 기록되지
않는다.

수집이 완료되면 원본 해시를 검증하고 스테이징 유니버스를 생성한다.

```powershell
python -m app.main krx-universe-build `
  --raw-dir output/krx_universe_raw `
  --output-dir output/universe_staging
```

KRX 원본 JSON은 감사와 재처리를 위해 그대로 보존한다. 빌드 단계에서는
기준일별 구성 종목을 이어 붙여 상장 기간과 시장 이전 구간을 복원한다.
V1 파생 유니버스에는 `주권 + 보통주`만 포함하고 우선주·스팩 등은
제외한다. 원본 응답에는 제외 대상도 그대로 보존된다.
