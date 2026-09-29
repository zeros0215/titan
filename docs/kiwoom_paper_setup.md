# 키움 모의투자 조회 연결 가이드

현재 구현 범위는 키움 REST API 모의투자 환경의 인증, 예수금 조회 및 KRX 평가잔고 조회입니다. 주문 API는 구현되어 있지 않으며, 조회가 성공해도 신규 주문은 계속 차단됩니다.

## 1. 키움에서 준비할 항목

1. 키움증권 계좌와 HTS ID를 준비합니다.
2. [키움 REST API 포털](https://openapi.kiwoom.com/main/home)에서 API 서비스를 신청합니다.
3. 모의투자를 별도로 신청합니다.
4. `모의투자 App Key 관리`에서 사용할 PC의 공인 IP를 등록합니다.
5. 모의투자용 App Key와 App Secret을 내려받아 안전하게 보관합니다.

실전용과 모의투자용 키는 서로 다릅니다. 이 프로젝트에는 반드시 모의투자용 키만 입력합니다. App Key와 App Secret은 다운로드 기회가 제한될 수 있으므로 원본 파일을 안전한 개인 저장소에 보관합니다.

- [공식 서비스 이용안내](https://openapi.kiwoom.com/intro/serviceInfo)
- [공식 모의투자 안내](https://openapi.kiwoom.com/intro/mockInvestInfo)

## 2. 로컬 환경 설정

프로젝트 루트의 `.env`에 다음 두 항목을 추가합니다.

```dotenv
KIWOOM_PAPER_APP_KEY=모의투자용_App_Key
KIWOOM_PAPER_APP_SECRET=모의투자용_App_Secret
```

주의사항:

- 실전용 키를 입력하지 않습니다.
- 키를 채팅, 화면 캡처, 로그 또는 Git에 남기지 않습니다.
- `.env.example`에는 실제 값을 입력하지 않습니다.
- 계좌번호는 설정할 필요가 없습니다. 키움에서 App Key에 등록한 모의계좌를 사용합니다.

## 3. 대시보드 실행과 동기화

```powershell
python -m tools.kis_dashboard_server
```

브라우저에서 `http://127.0.0.1:8765`를 열고 다음 순서로 확인합니다.

1. `키움 모의투자` 탭을 선택합니다.
2. `키움 모의계좌 동기화`를 누릅니다.
3. 연결 상태, 주문 가능금액, 평가금액과 보유 종목을 확인합니다.

정상 조회 후 예상 상태:

- 키움 연결: `연결됨`
- 잔고 동기화: `정상`
- 신규 주문: `차단`
- Kill Switch: `활성`
- 차단 사유: `ORDER_EXECUTION_NOT_IMPLEMENTED`

마지막 세 항목은 현재 단계에서 정상입니다. 주문 경계와 장애 복구 검증이 끝나기 전에는 해제하지 않습니다.

## 4. 현재 적용된 안전장치

- 기본 도메인은 `https://mockapi.kiwoom.com`으로 고정됩니다.
- 실전 도메인 `https://api.kiwoom.com`을 전달하면 클라이언트 생성 자체가 실패합니다.
- OAuth 토큰은 메모리에만 보관하며 대시보드 상태 파일에 기록하지 않습니다.
- 허용된 TR은 접근토큰 발급 `au10001`, 예수금 `kt00001`, 평가잔고 `kt00018`뿐입니다.
- 평가잔고는 `KRX`로만 조회합니다.
- 상태 파일에 계좌번호, App Secret 또는 토큰 필드가 들어오면 게시를 거부합니다.
- 모의투자 TR별 초당 1회 제한을 지킵니다.

## 5. 오류 확인

| 표시 코드 | 확인할 사항 |
|---|---|
| `PAPER_CREDENTIALS_MISSING` | `.env`의 모의 App Key와 App Secret 존재 여부 |
| `PAPER_AUTH_FAILED` | 모의 키인지, 키가 정확한지, API 신청 상태인지 확인 |
| `PAPER_AUTH_TRANSPORT_ERROR` | 인터넷 연결, 방화벽 및 키움 서비스 상태 확인 |
| `PAPER_ACCOUNT_READ_FAILED` | 모의계좌 등록과 API 응답 메시지 확인 |
| `PAPER_DASHBOARD_INVALID` | 상태 스키마 또는 민감정보 포함 여부 확인 |

키움 접근토큰은 공식 안내상 24시간 유효합니다. 프로그램은 만료 전에 새 토큰을 발급하며, 토큰 값을 파일이나 화면에 표시하지 않습니다.

## 6. 다음 개발 단계

계좌 조회가 정상임을 확인한 다음 내부 실패주입용 모의 브로커와 주문 조정기를 먼저 검증합니다. 이후에만 키움 모의 주문 API를 연결합니다. 실전 주문 도메인은 이 과정에 포함하지 않습니다.
