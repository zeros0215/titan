# TITAN 일일 운영 자동화

`daily` 명령은 기존의 Context + Feature 선정 목표와 전략 규칙을 변경하지
않고 다음 작업을 한 번에 수행한다.

1. 기준일의 선정 및 관찰 코호트 생성
2. 과거 스냅샷 중 5·10·20·40 거래일이 지난 항목 탐색
3. 아직 검증하지 않은 보유기간만 선정/관찰 코호트별로 분리 검증
4. 실행 상태는 `output/runs`, 실패 상세는 `output/failures`에 저장
5. 일일 운영 보고서를 `output/reports`에 저장

```powershell
python -m app.main daily --date 2026-07-28
```

동일한 기준일과 전략 버전에서 `COMPLETED` 또는 `PARTIAL` 실행이 있으면
중복 실행하지 않는다. 운영자가 의도적으로 다시 실행할 때만 `--force`를
사용한다.

KIS 모드에서는 한국투자증권의 국내 휴장일 조회 API를 사용하며 결과는
`cache/krx_sessions.json`에 저장한다. API 장애 시 캐시와 평일 캘린더로
계속 운영하고 일일 보고서에 경고를 남긴다. 최종 만기일은 실제 수집 시세의
거래 세션으로 다시 확인하므로 미래 데이터가 사용되지는 않는다.
KIS 권고에 맞춰 한 번의 일일 운영에서 휴장일 API는 최대 한 번만 호출한다.

선정 및 각 검증은 일시적 오류에 대비해 기본 2회까지 시도한다. 실패한 개별
검증은 다른 검증을 중단시키지 않는다. 일부 작업만 성공하면
`PARTIAL`, 아무 작업도 성공하지 못하면 `FAILED`로 기록한다.

## Windows 작업 스케줄러

당일 작업을 직접 실행할 때:

```powershell
powershell -NoProfile -File .\tools\run_daily.ps1
```

평일 오후 6시 30분 작업을 등록할 때 관리자 PowerShell에서:

```powershell
.\tools\install_daily_task.ps1 -RunAt "18:30"
```

Python 실행 파일이 시스템 경로에 없다면 작업을 등록하기 전에
`TITAN_PYTHON` 환경 변수에 가상환경의 `python.exe` 절대 경로를 설정한다.
등록 스크립트는 사용자가 명시적으로 실행할 때만 시스템 작업을 변경한다.

## KIS 읽기 전용 검증

```powershell
python -m tools.verify_kis_readonly `
  --stock-code 005930 `
  --stock-name "Samsung Electronics" `
  --days 180
```

이 진단은 토큰, 휴장일, KOSPI/KOSDAQ 지수와 종목 일봉만 조회하며 주문
API를 호출하지 않는다. VIRTUAL 환경에서 휴장일 TR `EGW02006`은
지원 범위 제한으로 처리하고 다른 검증을 계속한다.
