# TITAN 정식 승격 준비 상태

이 문서는 후보 전략을 정식 운영 대상으로 승격하기 전에 확인할 공통
체크리스트다. 실행 결과가 좋아도 데이터와 감사 조건이 충족되지 않으면
승격하지 않는다.

## 현재 판정

- 전략: `V1.3-S80-N7-TP5-SL10-CANDIDATE`
- 실주문: 미지원
- 활성 데이터 상태: `PROVISIONAL`
- 정식 백테스트 준비: `false`
- 로컬 활성 유니버스: 2022-01-01~2026-09-28 범위에 대해 매니페스트가
  `point_in_time_complete=true`, `source_complete=true`를 선언

유니버스 완료 선언과 별개로 활성 데이터 전체는 `PROVISIONAL`이다. 현재 활성
데이터 매니페스트가 기록한 차단 사유는 KRX 가격 원천에 공식 수정주가 필드가
없어서, 추론된 기업행위와 품질 격리 구간을 검토해야 한다는 점이다. 코드나
문서에서 전체 상태를 임의로 `READY`로 바꾸면 안 된다.

## 2026-09-29 가격 품질 감사

`price_history.review.review_price_quality`로 활성 가격 디렉터리를 다시
검사했다.

- 종목 파일 2,727개와 매니페스트 수량 일치
- 추론 조정 사건 676건, 조정계수 산술·연속성 규칙 오류 0건
- 미해결 가격 급변 527건 모두 격리 구간에 포함
- 격리 구간 486개, 거부 원시 행 4개와 매니페스트 수량 일치
- 공식 수정주가 근거가 없는 종목 파일 2,727개
- 공식 근거 대기 사건 1,203건
- 최신 수집일까지 종료되지 않은 격리 32개(기업행위 미해결 19개 포함)

기계 감사의 `PASS`는 파일 수량, 조정 산술 및 격리 적용의 내부 일관성만
뜻한다. 기업행위가 실제로 발생했는지를 승인하거나 정식 백테스트 준비 상태로
전환하지 않는다. 상세 결과는 `output/reports/price_quality_review.md`, 사건별
검토 큐는 `output/reports/price_quality_review_queue.csv`에 생성된다.

검토 우선순위는 다음과 같다.

1. 2022~2026 백테스트 대상 기간의 `UNRESOLVED_CORPORATE_ACTION`
2. 격리 종료일이 최신 수집일과 같은 미종결 구간
3. 조정 연속성 허용 범위 0.75 또는 1.25에 가까운 추론 사건
4. 동일 종목에서 반복 발생한 사건
5. 나머지 추론 조정과 장기 거래정지 후 불연속

활성 데이터를 변경하지 않고 감사를 다시 실행하려면:

```powershell
python -m tools.audit_active_price_quality
```

## 데이터 준비

- [ ] 공식 출처의 데이터셋 ID, 증거 URL, 취득 시각과 원본 해시 보존
- [ ] 요청 기간 전체의 신규상장·상장폐지·시장 이전 포함 확인
- [ ] 시점별 KOSPI/KOSDAQ 구성과 Top 500 산출 재현
- [ ] 거래정지, 관리종목, 스팩, 우선주 제외 근거 검토
- [ ] 액면분할·병합·배당 등 기업행위와 수정주가 근거 검토
- [ ] 품질 격리 구간을 종목·날짜 단위로 승인 또는 교정
- [ ] 거래비용·세금·슬리피지가 실제 계좌 가정과 일치하는지 확인

수집과 빌드는 다음의 재개 가능한 단계로 수행한다.

```powershell
python -m app.main krx-universe-collect --start 2022-01-03 --end 2025-12-31 --raw-dir output/krx_universe_raw --max-requests 5000
python -m app.main krx-universe-build --raw-dir output/krx_universe_raw --output-dir output/universe_staging
python -m app.main krx-price-collect --start 2022-01-03 --end 2025-12-31 --raw-dir output/krx_price_raw --max-requests 5000
python -m app.main krx-price-build --universe-raw-dir output/krx_universe_raw --price-raw-dir output/krx_price_raw --output-dir output/price_staging
```

수집에는 `KRX_AUTH_KEY`와 공식 서비스 사용 승인이 필요하다. 인증키는 파일이나
매니페스트에 기록하지 않는다.

## 검증 및 승격

- [ ] `python -m pytest` 전체 통과
- [ ] `backtest-preflight`의 모든 차단 조건 해소
- [ ] 동일 기간·비용·진입/청산 조건의 기준/후보 Walk-forward 완료
- [ ] 결과와 전략 사양의 SHA-256 및 재현성 검사 통과
- [ ] 최소 표본, 데이터 완료율, 양의 초과수익과 폴드 안정성 충족
- [ ] KIS 읽기 전용 파일럿과 forward-paper 표본 검토
- [ ] 변경 게이트의 `PASSED` 상태와 사람의 명시적 `APPROVED` 기록

데이터 승격은 검토가 끝난 별도 스테이징 디렉터리에 대해서만 수행한다.

```powershell
python -m app.main backtest-data-promote `
  --universe-dir output/universe_staging `
  --price-dir output/price_staging
python -m app.main backtest-preflight
```

## 운영 보존 원칙

- 원시 응답, 소스 매니페스트, 해시와 승인 기록은 감사 기간 동안 보존한다.
- 재생성 가능한 HTML·임시 리포트는 원시 데이터와 분리한다.
- `output/`은 Git에 커밋하지 않으므로 별도 백업 대상과 보존 기간을 정한다.
- 정리 작업은 활성 데이터 매니페스트가 참조하는 디렉터리를 삭제해서는 안 된다.
- 실패 실행도 성공 실행과 동일하게 보존해 선택적 결과 보고를 방지한다.

