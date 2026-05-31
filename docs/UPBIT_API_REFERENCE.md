# Upbit Open API 레퍼런스

[auto](..) 자동매매 봇이 사용하는 업비트 Open API 엔드포인트, 인증 헤더 생성 가이드, Rate Limit 및 KRW 마켓 관련 실무 요약 문서입니다.

---

## 📌 Upbit API 인프라 요약

### 🌐 API Base URL
| 유형 | 주소 | 비고 |
| :--- | :--- | :--- |
| **REST API** | `https://api.upbit.com/v1` | POST 요청은 JSON 전송 필수 (Form 방식 지원 종료) |
| **WebSocket 시세 (공개)** | `wss://api.upbit.com/websocket/v1` | 현재가 ticker 및 분 캔들 실시간 캐싱용 |
| **WebSocket 개인 (인증)** | `wss://api.upbit.com/websocket/v1/private` | 자산 잔고 및 주문 접수/체결 실시간 캐싱용 (자산/주문 WS는 기본 비활성 — `UPBIT_WS_ASSET_ENABLED`/`UPBIT_WS_ORDER_ENABLED` 기본 `False`. 주문 상태 캐시는 항상 `None`을 반환하고 상태 판정은 REST가 authoritative) |
| **보안 환경** | TLS 1.2 이상 필수 | — |

### 🔐 API 인증 방식
| 항목 | 사양 | 상세 |
| :--- | :---: | :--- |
| **토큰 규격** | JWT (HS512) | API Key 대조용 |
| **인증 헤더** | `Authorization: Bearer {token}` | REST 및 Private WS 요청에 적용 |
| **API 키 구성** | Access Key / Secret Key 쌍 | 발급 후 IP 화이트리스트 등록 필수 |
| **접속 허용 IP** | 단일 API Key 당 최대 10개 | — |

### ⏱ Rate Limit (초당 요청 제한)
| 그룹 유형 | 대상 API 예시 | 제한 건수 | 제한 기준 |
| :--- | :--- | :---: | :---: |
| **ticker** (시세) | `GET /v1/ticker` | 10 req / sec | 호출 IP 기준 |
| **default** (기본) | `GET /v1/accounts`, `GET /v1/order`, `DELETE /v1/order` 등 | 30 req / sec | 계정 기준 |
| **order** (주문) | `POST /v1/orders`, `POST /v1/orders/cancel_and_new` | 8 req / sec | 계정 기준 |
| **order-test** (테스트) | `POST /v1/orders/test` | 8 req / sec | 계정 기준 |
| **order-cancel-all** (일괄취소) | `DELETE /v1/orders` | 1 req / 2 sec | 계정 기준 |

### 🚨 공통 에러 및 주문 상태값
| 구분 | 값 | 상세 설명 |
| :--- | :---: | :--- |
| **오류 코드 429** | Too Many Requests | 단기간 요청 초과 (헤더 `Remaining-Req` 확인 필요) |
| **오류 코드 418** | Temporary Lockout | 429 반복 초과 시 발생하며 접속 일시/영구 차단 위험 |
| **주문 상태: wait** | 대기 | 거래소에 접수되어 체결을 기다리는 상태 |
| **주문 상태: watch** | 예약 | 예약가 주문이 활성화되길 기다리는 상태 |
| **주문 상태: done** | 체결 완료 | 주문 수량이 모두 체결된 최종 완료 상태 |
| **주문 상태: cancel** | 취소 | 체결 전 사용자에 의해 취소 완료된 최종 상태 |

---

## 문서 목적

이 문서는 자동매매 봇 소스 코드에서 사용하는 업비트 Open API 인터페이스를 신속하게 대조하기 위해 정리한 실무 지침서입니다.
- **공식 문서 확인 기준일**: 2026-05-04 (API v1.6.2 계열 기준)
- **우선순위**: 본 요약문과 업비트 공식 개발자 문서의 내용이 상충할 경우, **업비트 공식 개발자 문서가 절대 우선**합니다.

> [!NOTE]
> **공식 개발자 센터 진입점**:
> - 한국어 개발 가이드: [docs.upbit.com/kr](https://docs.upbit.com/kr)
> - LLM 지원 텍스트 명세: [docs.upbit.com/kr/llms.txt](https://docs.upbit.com/kr/llms.txt)

---

## 이 저장소 기준 구현 범위

- **설정**: [settings.py](../app/config/settings.py) 내 `EXCHANGE_TYPE = "crypto"` 지정 시 작동
- **핵심 연동 소스**:
  - **REST API 구현**: [crypto.py](../app/exchange/crypto.py)
  - **WebSocket 캐시 구현**: [upbit_ws.py](../app/exchange/upbit_ws.py)
  - **메인 평가 루프**: [main.py](../app/main.py)

---

## API 인증 헤더 생성 가이드

Exchange API 호출을 위해서는 JWT 토큰 생성이 요구됩니다.

### 1. JWT Payload 필드 구성
```json
{
  "access_key": "YOUR_UPBIT_ACCESS_KEY",
  "nonce": "REQ_UUID_STRING",
  "query_hash": "SHA512_HASH_OF_QUERYSTRING",
  "query_hash_alg": "SHA512"
}
```

### 2. `query_hash` 생성 규칙
- **GET / DELETE**: 
  요청 URL에 실려 나가는 쿼리 파라미터 문자열을 순서 변경 없이 그대로 사용합니다. 다중 배열 파라미터(`uuids[]` 등)는 동일한 키를 반복해서 표현합니다. 해시 연산 전에는 URL 디코딩이 완료된 평문 문자열을 기준으로 합니다.
- **POST (Body JSON)**: 
  JSON 데이터를 쿼리 파라미터 형식(`key=value&key2=value2`)으로 평탄화한 문자열로 변경하여 SHA-512 해싱합니다.
  *(예시: `market=KRW-BTC&side=bid&volume=0.01&price=100.0&ord_type=limit`)*

> [!WARNING]
> **비밀 서명 값 보호**: 
> JWT 서명 시 사용되는 Secret Key는 Base64 디코딩 절차 없이 그대로 문자열 바이트로 서명에 사용하며, 절대 외부로 유출되거나 형상 관리에 업로드되지 않도록 주의해야 합니다.

---

## 연동 엔드포인트 목록

봇과 API 서버에서 사용하는 API 목록입니다.

| 대상 기능 | HTTP Method | API Path | 인증 필요 | 관련 파일 및 연결부 |
| :--- | :---: | :--- | :---: | :--- |
| **현재가 단건 조회** | GET | `/v1/ticker` | 불필요 | [crypto.py](../app/exchange/crypto.py)::`get_current_price` |
| **분 캔들 조회** | GET | `/v1/candles/minutes/{unit}` | 불필요 | [crypto.py](../app/exchange/crypto.py)::`get_minute_candle_closes` |
| **계정 잔고 조회** | GET | `/v1/accounts` | **필요** | [crypto.py](../app/exchange/crypto.py)::`get_balance` |
| **주문 가능 정보** | GET | `/v1/orders/chance` | **필요** | [crypto.py](../app/exchange/crypto.py)::`place_order` 사전 검증 |
| **신규 주문 생성** | POST | `/v1/orders` | **필요** | [crypto.py](../app/exchange/crypto.py)::`place_order` |
| **주문 형식 검증** | POST | `/v1/orders/test` | **필요** | 주문 제출 전 모의 사전 테스트 검증 |
| **단건 주문 조회** | GET | `/v1/order` | **필요** | [crypto.py](../app/exchange/crypto.py)::`get_order_status` |
| **단건 주문 취소** | DELETE | `/v1/order` | **필요** | [crypto.py](../app/exchange/crypto.py)::`cancel_order` |
| **대기 주문 목록** | GET | `/v1/orders/open` | **필요** | 미체결 주문 동기화 및 부외 주문 대조 취소 |
| **종료 주문 목록** | GET | `/v1/orders/closed` | **필요** | 과거 주문/체결 완료 이력 동기화 검증 |

> [!NOTE]
> 리셋 스크립트([reset_live.py](../scripts/reset_live.py))는 일괄 취소 API(`DELETE /v1/orders`)를 쓰지 않습니다. 미체결 주문을 [crypto.py](../app/exchange/crypto.py)::`cancel_order`를 통해 **단건(`DELETE /v1/order`)으로 순회 취소**합니다.

### 참고용 (업비트 제공, 현재 봇 미사용)

아래 엔드포인트는 업비트가 제공하지만 본 저장소 코드 어디에서도 호출하지 않습니다. 향후 확장 시 참고용으로만 정리합니다.

| 대상 기능 | HTTP Method | API Path | 인증 필요 | 비고 |
| :--- | :---: | :--- | :---: | :--- |
| **선택 주문 조회** | GET | `/v1/orders/uuids` | **필요** | ID 배열을 전달해 다수 주문 일괄 상태 조회 (봇 미사용) |
| **선택 주문 취소** | DELETE | `/v1/orders/uuids` | **필요** | ID 배열을 전달해 다수 주문 일괄 취소 (봇 미사용) |
| **주문 일괄 취소** | DELETE | `/v1/orders` | **필요** | 미체결 주문 전체 취소 (봇 미사용; 리셋은 단건 `DELETE /v1/order` 순회) |
| **취소 후 재주문** | POST | `/v1/orders/cancel_and_new` | **필요** | 기존 주문 취소와 동시에 신규 지정가 교체 발주 (봇 미사용) |

---

## 1. 시세 (Quotation) API 명세

### 1-1. 현재가 조회 (`GET /v1/ticker`)
- **Query Parameter**: `markets` (필수, 예: `KRW-BTC`)
- **봇 제어 방식**:
  - `UPBIT_WS_PUBLIC_ENABLED=true` 설정 시, REST API 호출을 중단하고 WebSocket `ticker` 스트림으로부터 캐싱한 최신 데이터를 우선 참조합니다.
  - WebSocket 의존성 누락, 시작 실패, 연결 오류, 이벤트 없음, stale tick 상황에서는 `PRICE_POLL_INTERVAL=5` 설정에 따라 5초 주기의 REST ticker 요청 방식으로 자동 Fallback 구동됩니다.

### 1-2. 분 캔들 조회 (`GET /v1/candles/minutes/{unit}`)
- **Path Parameter**: `unit` (필수, 예: `15`)
- **Query Parameter**: `market` (필수), `count` (선택)
- **봇 제어 방식**:
  - 브레이크아웃 가드 기능에서 분봉 추세를 판단하기 위해 15분 단위 종가를 수집합니다.
  - 종가는 응답 내 `trade_price` 데이터를 참조합니다.

---

## 2. 주문 (Exchange) API 명세

### 2-1. 주문 요청 (`POST /v1/orders`)
- **핵심 파라미터 규격**:
  | 이름 | 타입 | 필수 여부 | 상세 범위 / 설정값 설명 |
  | :--- | :---: | :---: | :--- |
  | `market` | string | 필수 | 대상 시장 페어 코드 (예: `KRW-BTC`) |
  | `side` | string | 필수 | 주문 방향: `bid`(매수) / `ask`(매도) |
  | `ord_type` | string | 필수 | `limit` (지정가) / `price` (시장가 매수) / `market` (시장가 매도) / `best` (최유리 지정가) |
  | `volume` | string | 조건부 | 주문 코인 수량 (시장가 매수 주문 `price` 시 생략 가능) |
  | `price` | string | 조건부 | 주문 단가 또는 총 예산액 (시장가 매도 주문 `market` 시 생략 가능) |
  | `time_in_force`| string | 선택 | 지정가 주문 만료 성향 옵션: `ioc` / `fok` / `post_only` |
  | `smp_type` | string | 선택 | 자전거래 체결 방지 유형: `cancel_maker` / `cancel_taker` / `reduce` |
  | `identifier` | string | 선택 | 봇이 관리할 고유 주문 식별자 문자열 (계정 유일값 지정 필요) |

- **봇 매매 시나리오 적용**:
  - 빈 슬롯 하락 매수 및 보유 재고 이익 실현(TP) 매도는 지정가(`limit`) 발주를 표준으로 합니다.
  - 상승 돌파 매수(`UPWARD_BUY_ENABLED`) 발생 시에는 지정가 대신 예산액 기준 시장가 매수(`price`) 방식을 수행합니다.
  - 주문 접수 후 DB의 잔고 상태 갱신은 접수 응답값이 아닌, 단건 주문 조회(`GET /v1/order`)에서 상태가 `done`으로 검증 완료된 잔량을 기초로 하여 업데이트합니다.

---

## ⏱ Rate Limit 및 장애 차단 통제 정책

- **초과 에러 대응**: 
  `429` 또는 `418` 코드가 반환되면 봇은 즉시 추가 거래 요청을 중단하고 수 초간 쿨다운 지연을 가집니다. 지연 없이 루프 상에서 무차별 재시도를 반복할 경우 계정 API Key가 영구 차단될 위험이 있으므로 호출 제어가 필요합니다.
- **WebSocket 제한**: 
  WebSocket 접속은 초당 5회로 엄격하게 제어되며, 시세/개인 데이터 구독 메시지 전송은 분당 100회 한도로 제한됩니다.
- **해더 기반 제어**: 
  REST API 응답 헤더 내 `Remaining-Req` 필드에 기재된 초당 가용 잔여 요청 수치를 실시간 모니터링하여 가용율을 자동 스케일링하는 방식을 권장합니다.

---

## 💸 KRW 마켓 주문 정밀 정보

### 1. 최소 주문 가능액
- 원화 마켓 최소 발주 금액은 **5,000 KRW**로 통제됩니다.

### 2. 가격별 호가 단위 규정
주문 제출 단가는 아래의 가격 구간별 기준 단위로 절사 보정되어야 하며, 단위 불일치 주문 제출 시 즉시 거래소 에러를 반환합니다.

| 가격 구간 (KRW) | 최소 호가 변동 단위 (Tick size) |
| :--- | :---: |
| **2,000,000 이상** | 1,000 |
| **1,000,000 ~ 2,000,000 미만** | 1,000 |
| **500,000 ~ 1,000,000 미만** | 500 |
| **100,000 ~ 500,000 미만** | 100 |
| **50,000 ~ 100,000 미만** | 50 |
| **10,000 ~ 50,000 미만** | 10 |
| **5,000 ~ 10,000 미만** | 5 |
| **1,000 ~ 5,000 미만** | 1 |
| **100 ~ 1,000 미만** | 1 |
| **10 ~ 100 미만** | 0.1 |
| **1 ~ 10 미만** | 0.01 |
| **0.1 ~ 1 미만** | 0.001 |
| **0.01 ~ 0.1 미만** | 0.0001 |
| **0.001 ~ 0.01 미만** | 0.00001 |
| **0.0001 ~ 0.001 미만** | 0.000001 |
| **0.00001 ~ 0.0001 미만** | 0.0000001 |
| **0.00001 미만** | 0.00000001 |

> [!NOTE]
> 호가 간격은 마켓 종류와 무관하게 **가격대로만 결정**됩니다. 가격대가 100만 원 이상이면 **1,000원 단위**로 고정되고, 현재 마켓인 KRW-USDT처럼 시세가 1,000~5,000원 구간에 있으면 **1원 단위**가 적용됩니다.

---

## 🛠 안전 가동 핵심 체크리스트

1. [main.py](../app/main.py)를 단독 실행하는 조치는 실주문 발주가 이루어질 수 있으므로 개발 테스트 시에는 반드시 업비트 모의 테스트 모듈(`orders/test`)을 경유하거나 가상 환경 모의 검증(Mock test) 환경을 이용하세요.
2. 모든 API Key, DB 접속 정보 등은 형상 관리 유출 방지를 위해 [.env](../.env)를 통해 환경변수로 주입하여 운영하고, 디버깅 로그에 중요 Key의 평문이 찍히지 않도록 마스킹 처리하여 보존해야 합니다.
3. 주문 생성 후 네트워크 타임아웃 등으로 정상 응답 수집에 실패하여 누락된 거래가 의심되는 경우, 임의 재주문을 내지 말고 고유 식별자(`identifier`) 필드를 대조해 `/v1/order`로 먼저 재조회하여 복구 판정을 수행해야 합니다.
