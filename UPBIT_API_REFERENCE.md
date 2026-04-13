# UPBIT_API_REFERENCE.md

## 목적

이 문서는 현재 저장소에서 사용하는 업비트 Open API 관련 내용을 빠르게 참고하기 위한 **실무용 요약본**이다.

- 기준일: 2026-04-13
- 기준 범위: 가상화폐 거래, 업비트 거래소, REST API 중심
- 우선 대상: 현재 코드에서 직접 쓰는 인증/현재가/잔고/주문 생성/주문 조회/주문 취소
- 충돌 시 우선순위: 이 문서보다 **업비트 공식 문서가 우선**

이 문서는 공식 문서 전체 복제본이 아니라, 현재 프로젝트 구현에 필요한 핵심 내용을 정리한 내부 참고용 메모다.

## 공식 문서 진입점

- 개발자 센터: <https://docs.upbit.com/kr>
- 문서 인덱스: <https://docs.upbit.com/kr/llms.txt>
- 인증: <https://docs.upbit.com/kr/reference/auth>
- REST 사용/에러 안내: <https://docs.upbit.com/kr/reference/rest-api-guide>
- 요청 수 제한: <https://docs.upbit.com/kr/kr/reference/rate-limits>
- REST API Best Practice: <https://docs.upbit.com/kr/docs/rest-api-best-practice>
- 원화(KRW) 마켓 주문 가격 단위 / 최소 주문 가능 금액: <https://docs.upbit.com/kr/kr/docs/krw-market-info>

### 자주 보는 Reference

- 현재가 조회: <https://docs.upbit.com/kr/kr/reference/list-tickers>
- 잔고 조회: <https://docs.upbit.com/kr/reference/get-balance>
- 주문 가능 정보 조회: <https://docs.upbit.com/kr/reference/available-order-information>
- 주문 생성: <https://docs.upbit.com/kr/reference/new-order>
- 주문 생성 테스트: <https://docs.upbit.com/kr/reference/order-test>
- 개별 주문 조회: <https://docs.upbit.com/kr/reference/get-order>
- 개별 주문 취소: <https://docs.upbit.com/kr/reference/cancel-order>
- 체결 대기 주문 목록 조회: <https://docs.upbit.com/kr/reference/list-open-orders>

## 이 저장소 기준 범위

- 거래 자산: 가상화폐
- 기준 거래소: 업비트
- 현재 설정: `config/settings.py`의 `EXCHANGE_TYPE = "crypto"`
- 현재 구현 중심 파일:
  - `exchange/crypto.py`
  - `main.py`
  - `strategy/grid_strategy.py`

## API 큰 그림

업비트 API는 크게 두 범주로 나뉜다.

- Quotation API
  - 시세 조회용
  - 인증 없이 호출 가능
  - 예: 현재가, 캔들, 체결, 호가
- Exchange API
  - 계정/주문/자산 관리용
  - API Key 기반 인증 필요
  - 예: 잔고 조회, 주문 생성, 주문 조회, 주문 취소

현재 프로젝트는 둘 다 사용하지만, 핵심은 다음 흐름이다.

1. Quotation API로 현재가 조회
2. 내부 전략으로 매수/매도 판단
3. Exchange API로 잔고/주문 가능 여부 확인
4. Exchange API로 주문 생성
5. 필요 시 주문 조회/취소

## 기본 Endpoint

### REST

- Base URL: `https://api.upbit.com/v1`
- TLS 1.2 이상 필요
- POST 본문은 JSON으로 전송
- Form 방식 POST는 지원 종료

### WebSocket

- 시세용: `wss://api.upbit.com/websocket/v1`
- 내 자산/내 주문용: `wss://api.upbit.com/websocket/v1/private`

현재 저장소는 WebSocket을 아직 쓰지 않고 REST 중심이다.

## 인증 핵심 정리

### API Key

- 업비트 API Key는 Access Key / Secret Key 쌍으로 구성된다.
- 호출지 IP를 허용 목록에 등록해야 한다.
- API Key 당 최대 10개 IP를 등록할 수 있다.
- 필요한 권한 그룹을 API Key 발급 시 직접 부여해야 한다.

### JWT

- 인증이 필요한 Exchange API는 JWT 토큰을 `Authorization: Bearer {token}` 헤더로 보낸다.
- 업비트 문서는 JWT 서명 알고리즘으로 `HS512` 사용을 권장한다.
- Secret Key는 Base64 디코딩 없이 그대로 사용한다.

### JWT Payload 필드

- `access_key`: Access Key
- `nonce`: 요청마다 새로 만드는 UUID
- `query_hash`: 쿼리 문자열 또는 Body를 쿼리 문자열 형태로 바꾼 뒤 해시한 값
- `query_hash_alg`: 일반적으로 `SHA512`

### query_hash 생성 규칙

- GET / DELETE:
  - 실제 요청에 들어가는 쿼리 문자열 순서를 그대로 사용한다.
  - 파라미터를 임의로 재정렬하지 않는다.
  - `states[]`, `uuids[]` 같은 배열 파라미터는 키를 반복하는 형태로 만든다.
  - 해시 기준 문자열은 URL 인코딩을 풀어 둔 형태를 사용한다.
- POST:
  - JSON Body를 쿼리 문자열 형식으로 바꾼 뒤 해시한다.
  - 예: `market=KRW-BTC&side=bid&volume=0.01&price=100.0&ord_type=limit`

## 현재 프로젝트에서 직접 관련 있는 엔드포인트

| 기능 | Method | Path | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| 현재가 조회 | `GET` | `/v1/ticker` | 불필요 | `markets=KRW-BTC` 같은 형식 |
| 계정 잔고 조회 | `GET` | `/v1/accounts` | 필요 | `자산조회` 권한 |
| 주문 가능 정보 조회 | `GET` | `/v1/orders/chance` | 필요 | `주문조회` 권한 |
| 주문 생성 | `POST` | `/v1/orders` | 필요 | `주문하기` 권한 |
| 주문 생성 테스트 | `POST` | `/v1/orders/test` | 필요 | 실제 주문 없음 |
| 개별 주문 조회 | `GET` | `/v1/order` | 필요 | `uuid` 또는 `identifier` 중 하나 |
| 개별 주문 취소 | `DELETE` | `/v1/order` | 필요 | `uuid` 또는 `identifier` 중 하나 |
| 체결 대기 주문 조회 | `GET` | `/v1/orders/open` | 필요 | 미체결 주문 목록 |

## 현재가 조회

- 엔드포인트: `GET /v1/ticker`
- 용도: 특정 페어의 현재가 스냅샷 조회
- 예시 파라미터: `markets=KRW-BTC`
- 현재 코드 연결:
  - `exchange/crypto.py::get_current_price`

주의:

- 이 API는 스냅샷 조회다.
- 고빈도 실시간 전략이면 WebSocket 전환을 검토해야 한다.

## 잔고 조회

- 엔드포인트: `GET /v1/accounts`
- 권한: `자산조회`
- 용도: KRW 잔고와 보유 코인 잔고 확인
- 현재 코드 연결:
  - `exchange/crypto.py::get_balance`
  - `exchange/crypto.py::get_holdings`
  - `python3 main.py balance`

주의:

- 응답에는 사용 가능 잔고와 잠금 자산 정보가 함께 올 수 있다.
- 주문 생성 직후에는 주문에 사용된 자산이 잠금 상태가 될 수 있다.

## 주문 가능 정보 조회

- 엔드포인트: `GET /v1/orders/chance`
- 권한: `주문조회`
- 용도:
  - 주문 가능 여부 확인
  - 수수료율 확인
  - 최소/최대 주문 가능 금액 확인
  - 마켓이 지원하는 매수/매도 주문 타입 확인

권장 사용 시점:

- 실주문 전 사전 검증
- KRW 마켓 최소 주문 금액 확인
- 지원 주문 타입(`limit`, `market`, `best`) 및 옵션 확인

현재 코드에는 아직 직접 연결되어 있지 않다.

## 주문 생성

- 엔드포인트: `POST /v1/orders`
- 권한: `주문하기`

### 핵심 파라미터

- `market`: 예: `KRW-BTC`
- `side`
  - `bid`: 매수
  - `ask`: 매도
- `ord_type`
  - `limit`: 지정가
  - `price`: 시장가 매수
  - `market`: 시장가 매도
  - `best`: 최유리 지정가
- `volume`
- `price`
- `time_in_force`
  - `ioc`
  - `fok`
  - `post_only`
- `smp_type`
  - `cancel_maker`
  - `cancel_taker`
  - `reduce`
- `identifier`: 사용자 정의 주문 식별자

### 현재 저장소와 직접 관련 있는 주문 유형

- 현재 구현은 지정가 주문 중심이다.
- 코드상 매수는 `side=bid`, 매도는 `side=ask`로 매핑된다.
- 현재 `exchange/crypto.py::place_order`는 `ord_type=limit`만 사용한다.

### 주문 옵션 주의사항

- `post_only`는 지정가 주문에서만 사용 가능하다.
- `post_only`는 `smp_type`과 함께 사용할 수 없다.
- `identifier`는 계정 전체 주문 기준으로 유일해야 하며, 한번 사용한 값은 재사용하지 않는 편이 안전하다.

### 자산 잠금

- 매수 주문 생성 시 호가 자산이 잠긴다.
- 매도 주문 생성 시 기준 자산이 잠긴다.
- 잠금은 전량 체결, 취소, 또는 `time_in_force` 조건에 의한 만료 전까지 유지될 수 있다.

## 주문 생성 테스트

- 엔드포인트: `POST /v1/orders/test`
- 권한: `주문하기`
- 실제 주문을 만들지 않고 주문 형식과 주문 가능 상태를 검증한다.

이 저장소에서 실주문 기능을 계속 유지할 거라면, 향후 다음 순서가 안전하다.

1. `orders/chance`로 최소 주문 금액/주문 가능 상태 확인
2. `orders/test`로 주문 형식 검증
3. `orders`로 실제 주문 생성

현재 코드에는 아직 직접 연결되어 있지 않다.

## 개별 주문 조회 / 취소

### 개별 주문 조회

- `GET /v1/order`
- 권한: `주문조회`
- `uuid` 또는 `identifier` 중 하나가 필요하다.

### 개별 주문 취소

- `DELETE /v1/order`
- 권한: `주문하기`
- `uuid` 또는 `identifier` 중 하나가 필요하다.

현재 코드 연결:

- 조회는 `exchange/crypto.py::get_order_status`에서 사용한다.
- 취소는 `exchange/crypto.py::cancel_order`에서 사용한다.

## 체결 대기 주문 조회

- `GET /v1/orders/open`
- 권한: `주문조회`
- 미체결 주문 목록을 확인할 때 사용한다.

운영상 유용한 시점:

- 재시작 직후 미체결 주문 동기화
- 중복 주문 방지
- 장시간 대기 주문 정리

## 요청 수 제한

모든 요청 수 제한은 초 단위다. 같은 Rate Limit 그룹에 속한 API끼리는 허용량을 함께 공유한다.

현재 프로젝트에 직접 중요한 값만 정리하면 다음과 같다.

| API | 제한 |
| --- | --- |
| `GET /v1/ticker` | 초당 최대 10회, IP 단위 |
| `GET /v1/accounts` | 초당 최대 30회, 계정 단위 |
| `GET /v1/orders/chance` | 초당 최대 30회, 계정 단위 |
| `GET /v1/order` | 초당 최대 30회, 계정 단위 |
| `DELETE /v1/order` | 초당 최대 30회, 계정 단위 |
| `GET /v1/orders/open` | 초당 최대 30회, 계정 단위 |
| `POST /v1/orders` | 초당 최대 8회, 계정 단위 |
| `POST /v1/orders/test` | 초당 최대 8회, 계정 단위 |

구현 원칙:

- 응답 헤더 `Remaining-Req`를 보고 조절한다.
- `429 Too Many Requests`가 오면 즉시 같은 그룹 호출을 멈추고 대기한다.
- 반복 초과는 임시 또는 영구 제한으로 이어질 수 있으므로, 단순 재시도 루프를 만들지 않는다.

## KRW 마켓 운영 메모

- 원화(KRW) 마켓은 주문 가격 단위와 최소 주문 가능 금액 정책이 있다.
- 이 값은 가격대와 마켓 정책에 따라 달라질 수 있으므로, 고정 숫자를 코드에 박아두기보다 공식 문서와 `orders/chance`를 함께 확인하는 편이 안전하다.
- 그리드 전략에서 지정가를 생성할 때는 가격 단위 반올림/절사를 반드시 검토해야 한다.
- BTC 그리드 생성 시에도 KRW 마켓 호가 단위에 맞춰 가격을 보정하고, 최소 주문 가능 금액 `5,000 KRW` 이상인지 확인해야 한다.

## 이 저장소 기준 구현 체크리스트

- `python main.py`는 실제 주문을 발생시킬 수 있다.
- 테스트 목적이면 실주문 대신 다음을 우선한다.
  - `python3 -c "import main"`
  - `python3 main.py balance`
  - 주문 검증 전용 경로 추가
  - `POST /v1/orders/test` 사용
- API Key는 환경변수로만 주입한다.
- 로그에는 API Key, JWT, Secret Key를 남기지 않는다.
- 주문/조회/취소 코드는 권한 부족(`out_of_scope`)과 인증 오류를 분리해서 처리한다.
- 잔고 조회 결과만 믿고 바로 주문하지 말고, 필요하면 `orders/chance`와 미체결 주문 상태를 함께 본다.

## 향후 개선 후보

- `exchange/crypto.py`에 `orders/chance` 연동 추가
- 실주문 전 `orders/test` 사전 검증 추가
- `Remaining-Req` 파싱 및 throttling 추가
- 미체결 주문 조회(`orders/open`)를 통한 재시작 복구 로직 추가
- 가격 단위/최소 주문 금액을 KRW 마켓 정책 기준으로 정규화하는 유틸 추가

## 문서 갱신 방법

문서가 바뀌었는지 확인할 때는 다음 순서로 보면 된다.

1. `https://docs.upbit.com/kr/llms.txt`
2. 인증 / REST API 가이드 / Rate Limits
3. 현재 저장소가 실제로 호출하는 엔드포인트 문서
4. 주문 관련 changelog 또는 revision history

이 문서를 갱신할 때는 날짜를 함께 바꾼다.
