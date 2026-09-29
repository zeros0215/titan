# TITAN 실매매 준비 아키텍처

현재 단계는 키움 모의투자 인증과 계좌 조회까지만 연결하고 주문 도메인,
사전 위험관리 및 계좌 동기화 경계를 고정한다. 키움 주문 전송 구현은 없다.

## 경계

```text
Strategy / Signal
    -> OrderIntent
    -> RiskManager (기본 거부)
    -> BrokerOrderRequest
    -> OrderCoordinator (journal first)
    -> ExecutionBroker port
    -> 현재 SimulatedExecutionBroker / 향후 키움 모의주문 adapter

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
- `SimulatedExecutionBroker`는 실계좌나 키움 API를 호출하지 않고 정상 접수,
  전량·부분 체결, 거부, 접수 후 timeout 및 취소 경쟁 체결을 재현한다.
- `OrderCoordinator`는 intent, 위험판정 및 제출 시작을 내구성 저널에 기록한
  뒤에만 브로커를 호출한다. 제출 후 응답이 불명확하면 자동 재시도하지 않는다.
- 동일 fill ID 통지는 저널 조회로 중복 기록하지 않는다.

## KRX 주문 규칙

`MarketRulesSnapshot`은 주문 직전의 KRX 전용 규칙 스냅샷이다. 휴장일을
단순 요일 계산으로 추정하거나 가격제한폭을 애플리케이션이 임의 반올림하지
않고, 조회 계층이 확인한 정규장 상태·기준가·상한가·하한가와 해당 주문가격의
호가단위를 전달해야 한다.

- 규칙 스냅샷이 없거나 오래되면 `MARKET_RULES_MISSING` 또는
  `MARKET_RULES_STALE`로 거부
- KRX 이외 거래소와 정규장 외 주문 거부
- 지정가가 해당 가격의 호가단위와 맞지 않으면 거부
- 지정가가 당일 상·하한가 밖이면 거부
- 시장가는 지정가 필드를 가질 수 없다는 도메인 제약을 유지

키움 모의 주문 어댑터를 연결할 때 `RiskLimits.require_market_rules=true`를
필수로 사용한다. 현재 내부 모의 브로커의 단위 테스트만 이를 선택적으로
해제한다.

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

1. 운영자 kill switch와 수동 승인 화면
2. 계좌·미체결·체결 주기 동기화 및 장애 경보
3. 키움 모의 주문 adapter와 조회 기반 주문 상태 복구
4. 모의투자에서 부분체결·취소·응답 유실 통합 테스트
5. `PROVISIONAL` 데이터와 후보 전략의 정식 승격
6. 위 조건 완료 후에만 별도 실전 활성화 심사

실계좌 주문은 이 문서의 경계가 존재한다는 이유만으로 허용되지 않는다.
현재 운영 상태는 계속 주문 0건이다.
