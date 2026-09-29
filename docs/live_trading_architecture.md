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
- `ExecutionBroker`와 `ExecutionJournal`은 인터페이스뿐이며 구현되지 않았다.

## 실매매 활성화 전 남은 필수 작업

1. append-only 실행 저널과 재시작 복구
2. 모의 증권사 어댑터를 통한 부분체결·취소·응답 유실 테스트
3. 주문 제출 전 기록과 intent ID 기반 중복 방지의 트랜잭션 보장
4. 거래 세션, 호가 단위, 가격제한폭 및 주문 유형 검증
5. 운영자 kill switch와 수동 승인 화면
6. 계좌·미체결·체결 주기 동기화 및 장애 경보
7. `PROVISIONAL` 데이터와 후보 전략의 정식 승격
8. 위 조건 완료 후에만 별도 키움 어댑터 구현

실계좌 주문은 이 문서의 경계가 존재한다는 이유만으로 허용되지 않는다.
현재 운영 상태는 계속 주문 0건이다.
