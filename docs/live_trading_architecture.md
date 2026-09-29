# TITAN 실매매 준비 아키텍처

현재 단계는 증권사 API를 연결하지 않고 주문 도메인, 사전 위험관리 및 계좌
동기화 경계를 고정한다. `trading` 패키지에는 키움 인증, 시세 조회 또는 주문
전송 구현이 없다.

## 경계

```text
Strategy / Signal
    -> OrderIntent
    -> RiskManager (기본 거부)
    -> BrokerOrderRequest
    -> ExecutionBroker port
    -> 향후 별도 증권사 adapter

Broker AccountSnapshot
    + InternalPortfolioSnapshot
    -> ReconciliationResult
    -> 불일치가 하나라도 있으면 신규 주문 금지
```

- 전략은 `OrderIntent`만 만들고 증권사 호출을 할 수 없다.
- `RiskManager`는 계좌 동기화, kill switch, LIVE 이중 잠금, 시세·잔고
  신선도, 중복 의도, 주문/종목/총노출 한도, 일일 손실, 미체결 수 및 매도
  가능 수량을 확인한다.
- 금액과 가격은 이진 부동소수점 오차를 피하기 위해 `Decimal`을 사용한다.
- 모든 시각은 timezone-aware여야 한다.
- 증권사 상태와 로컬 상태가 다르면 `ReconciliationResult.ready=false`다.
- `ExecutionBroker`는 인터페이스뿐이며 구현되지 않았다.

## 실행 저널과 재시작 복구

`SQLiteExecutionJournal`은 PAPER/LIVE 환경과 마스킹된 계좌 별칭 하나에만
결합된다. 실제 계좌번호, 비밀번호, 토큰, App Key와 Secret은 payload에
기록할 수 없다.

- SQLite `synchronous=FULL`과 WAL 사용
- 이벤트 ID 고유성 및 `INTENT_RECORDED`의 intent ID 고유성 강제
- 이벤트 UPDATE/DELETE 차단 트리거
- 이전 이벤트 해시를 포함한 SHA-256 연속 해시
- `Decimal`은 문자열로 저장하고 `float` 입력은 거부
- 저널 무결성 오류 시 복구 결과의 kill switch를 강제로 활성화

연속 해시는 우발적 손상이나 해시를 다시 계산하지 않은 변조를 검출한다. DB
파일을 직접 수정할 권한이 있는 공격자가 전체 체인까지 다시 만드는 상황을
방지하려면 향후 마지막 해시를 별도 읽기 전용 저장소에도 고정해야 한다.

재시작할 때마다 새로운 `recovery_id`를 생성하고 다음 순서로 처리한다.

1. `recover_execution_state(..., recovery_id=<새 ID>)`로 저널을 재생한다.
2. 이전 프로세스의 계좌 동기화 기록은 새 기동을 승인하지 못한다.
3. 증권사 계좌·보유·미체결을 새로 조회하고 로컬 상태와 대조한다.
4. 결과를 같은 `recovery_id`의 `RECONCILIATION_COMPLETED` 이벤트로 기록한다.
5. 저널을 다시 재생해 `safe_to_trade=true`인지 확인한다.

제출 시작 후 접수 이벤트가 없는 주문은 실제 접수 여부를 알 수 없으므로
`UNKNOWN`으로 복구하고 신규 주문을 차단한다. 위험 승인 이벤트가 없는 제출,
중복 체결 ID, 요청 수량보다 많은 체결도 복구 오류다.

## 실매매 활성화 전 남은 필수 작업

1. 모의 증권사 어댑터를 통한 부분체결·취소·응답 유실 테스트
2. 주문 조정자에서 제출 전 기록과 intent ID 중복 방지를 트랜잭션으로 연결
3. 거래 세션, 호가 단위, 가격제한폭 및 주문 유형 검증
4. 운영자 kill switch와 수동 승인 화면
5. 계좌·미체결·체결 주기 동기화 및 장애 경보
6. `PROVISIONAL` 데이터와 후보 전략의 정식 승격
7. 위 조건 완료 후에만 별도 키움 어댑터 구현

실계좌 주문은 이 문서의 경계가 존재한다는 이유만으로 허용되지 않는다.
현재 운영 상태는 계속 주문 0건이다.
