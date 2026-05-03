# UPBIT_API_REFERENCE.md

## 목적

이 문서는 현재 저장소에서 사용하는 업비트 Open API 관련 내용을 빠르게 참고하기 위한 **실무용 요약본**이다.

- 기준일: 2026-04-24
- API 버전: v1.6.2 (공식 문서 기준)
- 기준 범위: 가상화폐 거래, 업비트 거래소, REST API 중심
- 우선 대상: 현재 코드에서 직접 쓰는 인증/현재가/잔고/주문 생성/주문 조회/주문 취소
- 충돌 시 우선순위: 이 문서보다 **업비트 공식 문서가 우선**

이 문서는 공식 문서 전체 복제본이 아니라, 현재 프로젝트 구현에 필요한 핵심 내용을 정리한 내부 참고용 메모다.

## 공식 문서 진입점

- 개발자 센터: <https://docs.upbit.com/kr>
- 문서 인덱스: <https://docs.upbit.com/kr/llms.txt>
- 인증: <https://docs.upbit.com/kr/reference/auth>
- REST 사용/에러 안내: <https://docs.upbit.com/kr/reference/rest-api-guide>
- 요청 수 제한: <https://docs.upbit.com/kr/reference/rate-limits>
- REST API Best Practice: <https://docs.upbit.com/kr/docs/rest-api-best-practice>
- 원화(KRW) 마켓 주문 가격 단위 / 최소 주문 가능 금액: <https://docs.upbit.com/kr/docs/krw-market-info>
- 자전거래 체결 방지(SMP): <https://docs.upbit.com/kr/docs/smp>

### 자주 보는 Reference

- 현재가 조회: <https://docs.upbit.com/kr/reference/list-tickers>
- WebSocket 가이드: <https://docs.upbit.com/kr/reference/websocket-guide>
- WebSocket 현재가: <https://docs.upbit.com/kr/reference/websocket-ticker>
- WebSocket 분 캔들: <https://docs.upbit.com/kr/reference/websocket-candle>
- WebSocket 내 자산: <https://docs.upbit.com/kr/reference/websocket-myasset>
- WebSocket 내 주문: <https://docs.upbit.com/kr/reference/websocket-myorder>
- 잔고 조회: <https://docs.upbit.com/kr/reference/get-balance>
- 주문 가능 정보 조회: <https://docs.upbit.com/kr/reference/available-order-information>
- 주문 생성: <https://docs.upbit.com/kr/reference/new-order>
- 주문 생성 테스트: <https://docs.upbit.com/kr/reference/order-test>
- 개별 주문 조회: <https://docs.upbit.com/kr/reference/get-order>
- 개별 주문 취소: <https://docs.upbit.com/kr/reference/cancel-order>
- 체결 대기 주문 목록 조회: <https://docs.upbit.com/kr/reference/list-open-orders>
- 종료 주문 목록 조회: <https://docs.upbit.com/kr/reference/list-closed-orders>
- ID로 주문 목록 조회: <https://docs.upbit.com/kr/reference/list-orders-by-ids>
- ID로 주문 목록 취소: <https://docs.upbit.com/kr/reference/cancel-orders-by-ids>
- 주문 일괄 취소: <https://docs.upbit.com/kr/reference/batch-cancel-orders>
- 취소 후 재주문: <https://docs.upbit.com/kr/reference/cancel-and-new-order>

## 이 저장소 기준 범위

- 거래 자산: 가상화폐
- 기준 거래소: 업비트
- 현재 설정: `app/config/settings.py`의 `EXCHANGE_TYPE = "crypto"`
- 현재 구현 중심 파일:
  - `app/exchange/crypto.py`
  - `app/exchange/upbit_ws.py`
  - `app/main.py`
  - `app/strategy/grid_strategy.py`

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

1. Public WebSocket `ticker` 이벤트를 수신해 최신 현재가 캐시 갱신
2. 최소 3초 간격 전략 평가 사이클에서 매수/매도 판단
3. Exchange API로 잔고/주문 가능 여부 확인
4. Exchange API로 주문 생성
5. 필요 시 REST 또는 terminal `myOrder` 캐시로 주문 조회, REST로 주문 취소

## 기본 Endpoint

### REST

- Base URL: `https://api.upbit.com/v1`
- TLS 1.2 이상 필요
- POST 본문은 JSON으로 전송
- Form 방식 POST는 지원 종료 (2022-03-01 이후)

### WebSocket

- 시세용(공개): `wss://api.upbit.com/websocket/v1`
- 내 자산/내 주문용(인증): `wss://api.upbit.com/websocket/v1/private`

현재 저장소는 현재가 조회용 `ticker` 캐시와 브레이크아웃 가드용 분 캔들 `candle.{unit}m` 캐시를 선택적으로 공개 WebSocket으로 쓴다. 잔고와 보유 수량은 선택적으로 인증 WebSocket `myAsset` 캐시를 쓸 수 있다. 주문 상태 조회는 선택적으로 인증 WebSocket `myOrder` 캐시를 terminal 상태(`done`, `cancel`)에만 보수적으로 쓸 수 있다. 현재가 `ticker` WebSocket과 ticker 이벤트 기반 메인 루프는 기본 활성화이며, 장애/의존성 없음/이벤트 없음이면 기존 REST polling으로 fallback 한다. 주문 생성과 취소는 계속 REST만 사용한다.

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
- `query_hash_alg`: 일반적으로 `SHA512` (기본값이므로 생략 가능)

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
| 현재가 조회 | `GET` | `/v1/ticker` | 불필요 | `markets=KRW-BTC` 같은 형식. 옵션 WebSocket ticker 캐시의 fallback |
| 분 캔들 조회 | `GET` | `/v1/candles/minutes/{unit}` | 불필요 | 현재 브레이크아웃 가드에서 `unit=15` 사용. 옵션 WebSocket candle 캐시의 fallback |
| 계정 잔고 조회 | `GET` | `/v1/accounts` | 필요 | `자산조회` 권한. 옵션 WebSocket myAsset 캐시의 fallback |
| 주문 가능 정보 조회 | `GET` | `/v1/orders/chance` | 필요 | `주문조회` 권한 |
| 주문 생성 | `POST` | `/v1/orders` | 필요 | `주문하기` 권한 |
| 주문 생성 테스트 | `POST` | `/v1/orders/test` | 필요 | 실제 주문 없음 |
| 개별 주문 조회 | `GET` | `/v1/order` | 필요 | `uuid` 또는 `identifier` 중 하나. 옵션 WebSocket myOrder 캐시의 fallback |
| 개별 주문 취소 | `DELETE` | `/v1/order` | 필요 | `uuid` 또는 `identifier` 중 하나 |
| 체결 대기 주문 조회 | `GET` | `/v1/orders/open` | 필요 | 미체결 주문 목록 |
| 종료 주문 목록 조회 | `GET` | `/v1/orders/closed` | 필요 | 체결/취소 완료 주문 목록 |
| ID로 주문 목록 조회 | `GET` | `/v1/orders/uuids` | 필요 | uuid 또는 identifier 배열 |
| ID로 주문 목록 취소 | `DELETE` | `/v1/orders/uuids` | 필요 | uuid 또는 identifier 배열 |
| 주문 일괄 취소 | `DELETE` | `/v1/orders` | 필요 | 전체 미체결 주문 취소 |
| 취소 후 재주문 | `POST` | `/v1/orders/cancel_and_new` | 필요 | 취소와 신규 주문 원자 실행 |

## 현재가 조회

- REST 엔드포인트: `GET /v1/ticker`
- 선택 기능: Public WebSocket `ticker` 캐시
- 용도: 특정 페어의 현재가 스냅샷 조회
- 예시 파라미터: `markets=KRW-BTC`
- 현재 코드 연결:
  - `app/exchange/crypto.py::get_current_price`
  - `app/exchange/crypto.py::wait_for_ticker_price_event`
  - `app/exchange/upbit_ws.py::UpbitTickerWebSocketCache`
  - `app/main.py::run_price_event_loop_iteration`

주의:

- `UPBIT_WS_PUBLIC_ENABLED=true` 가 기본값이며, ticker 캐시와 메인 이벤트 루프가 public WebSocket ticker를 우선 사용한다.
- `UPBIT_WS_EVENT_LOOP_ENABLED=true` 가 기본값이면 메인 루프는 새 ticker 이벤트를 기다렸다가 최신 가격으로 한 사이클을 실행한다.
- 이벤트 기반 전략 평가는 `UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=3` 기본값으로 최소 3초 간격 throttle을 적용한다.
- WebSocket callback/thread 는 가격 이벤트 캐시만 갱신하고, 주문/DB/전략 상태 변경은 `app/main.py`의 단일 루프에서 직렬 처리한다.
- WebSocket 의존성 누락, 시작 실패, 첫 tick 없음, 이벤트 timeout, stale tick 은 모두 기존 `PRICE_POLL_INTERVAL=5` REST ticker polling fallback 으로 처리한다.
- 주문 가능 정보, 주문 테스트, 주문 생성/취소는 계속 REST를 사용한다. 주문 상태 조회는 `UPBIT_WS_ORDER_ENABLED=true`일 때 terminal `myOrder` 이벤트만 REST 생략에 사용할 수 있다.

## 분 캔들 조회

- REST 엔드포인트: `GET /v1/candles/minutes/{unit}`
- 선택 기능: Public WebSocket `candle.{unit}m` 캐시
- 현재 프로젝트 사용값: `unit=15`
- 인증: 불필요
- 현재 코드 연결:
  - `app/exchange/crypto.py::get_recent_minute_closes`
  - `app/exchange/crypto.py::get_minute_candle_closes`
  - `app/exchange/upbit_ws.py::UpbitMinuteCandleWebSocketCache`
  - `app/main.py::fetch_breakout_guard_status`

핵심 메모:

- `market`, `count` 파라미터를 사용한다.
- 종가는 응답의 `trade_price` 필드를 사용한다.
- 분 캔들은 체결이 발생한 구간만 생성된다.
- 브레이크아웃 가드는 `get_minute_candle_closes(symbol, unit_minutes, count, to)`를 통합 지점으로 사용한다.
- WebSocket 캐시는 `to`를 exclusive cutoff로 보고, candle start가 `to`보다 엄격히 이전인 완료 캔들 종가만 반환한다.
- `UPBIT_WS_CANDLE_ENABLED=false` 가 기본값이며, 기본 동작은 기존 REST 캔들 조회와 같다.
- WebSocket 의존성 누락, 시작 실패, 첫 candle 없음, stale stream, 지원하지 않는 unit, 완료 캔들 부족은 모두 REST candle fallback 으로 처리한다.

## 잔고 조회

- 엔드포인트: `GET /v1/accounts`
- 선택 기능: Private WebSocket `myAsset` 캐시
- 권한: `자산조회`
- 용도: KRW 잔고와 보유 코인 잔고 확인
- 현재 코드 연결:
  - `app/exchange/crypto.py::get_balance`
  - `app/exchange/crypto.py::get_holdings`
  - `app/exchange/upbit_ws.py::UpbitAssetWebSocketCache`
  - `python3 main.py balance`

주의:

- 응답에는 사용 가능 잔고(`balance`)와 잠금 자산(`locked`) 정보가 함께 올 수 있다.
- 주문 생성 직후에는 주문에 사용된 자산이 잠금 상태가 될 수 있다.
- `get_balance()`는 `balance` 필드만 사용하므로 잠금 자산은 포함하지 않는다.
- `UPBIT_WS_ASSET_ENABLED=false` 가 기본값이며, 기본 동작은 기존 REST `/v1/accounts` 조회와 같다.
- 인증 WebSocket 엔드포인트는 `wss://api.upbit.com/websocket/v1/private` 이며, 기존 JWT 인증 헤더 생성 로직을 사용한다.
- `myAsset` 구독 메시지는 `codes`를 포함하지 않는다. 공식 문서 기준 `myAsset`에 `codes`를 넣으면 `WRONG_FORMAT` 오류가 날 수 있다.
- `myAsset`은 이벤트 기반이므로 시작 직후 첫 이벤트가 없을 수 있다. 첫 이벤트 없음, stale cache, 연결 오류, 의존성 누락, 인증 헤더 생성 실패는 모두 REST `/v1/accounts` fallback 으로 처리한다.
- 현재 구현은 `assets[].currency`, `assets[].balance`를 캐시하며, 0 잔고도 정상 값으로 취급한다.

## 주문 가능 정보 조회

- 엔드포인트: `GET /v1/orders/chance`
- 권한: `주문조회`
- 용도:
  - 주문 가능 여부 확인
  - 수수료율 확인
  - 최소/최대 주문 가능 금액 확인
  - 마켓이 지원하는 매수/매도 주문 타입 확인

주요 응답 필드:

- `bid_fee` / `ask_fee`: 테이커 매수/매도 수수료율
- `maker_bid_fee` / `maker_ask_fee`: 메이커 매수/매도 수수료율
- `market.bid_types`: 지원하는 매수 주문 타입 목록
- `market.ask_types`: 지원하는 매도 주문 타입 목록
- `market.order_types`: **지원 종료 예정** — `bid_types`, `ask_types` 사용 권장
- `market.max_total`: 최대 주문 가능 금액
- `bid_account` / `ask_account`: 호가/기준 자산 계정 잔고

권장 사용 시점:

- 실주문 전 사전 검증
- KRW 마켓 최소/최대 주문 금액 확인
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
  - `price`: 시장가 매수 (KRW 금액 지정)
  - `market`: 시장가 매도 (수량 지정)
  - `best`: 최유리 지정가 (2024-04-22 추가)
- `volume`: 주문 수량 (시장가 매수 제외 시 필수)
- `price`: 주문 단가 또는 KRW 총액 (시장가 매도 제외 시 필수)
- `time_in_force`
  - `ioc`: 즉시 체결 가능 수량만 부분 체결, 잔여 취소
  - `fok`: 전량 체결 가능할 때만 실행, 아니면 전량 취소
  - `post_only`: 메이커 주문으로만 생성 (지정가 전용, 2025-07-07 추가)
- `smp_type`: 자전거래 체결 방지 (2025-07-02 추가)
  - `cancel_maker`: 새 주문 생성 시 기존 주문 취소
  - `cancel_taker`: 새 주문 생성 시 신규 주문 취소
  - `reduce`: 양쪽 주문 수량 감소
- `identifier`: 사용자 정의 주문 식별자 (계정 전체 유일, 2024-12-04 추가)

### 현재 저장소와 직접 관련 있는 주문 유형

- 현재 그리드 전략 경로는 지정가 주문과 조건부 시장가 예산매수를 함께 사용한다.
- 코드상 매수는 `side=bid`, 매도는 `side=ask`로 매핑된다.
- 빈 슬롯 하락 교차 매수와 보유 슬롯 매도는 `ord_type=limit`를 사용한다.
- 빈 슬롯은 `previous_price > buy_price >= current_price` 인 하락 교차일 때 지정가 주문을 낸다.
- 한 평가 사이클 안에 여러 `buy_price`를 아래로 동시에 통과하면 그 empty 슬롯들은 모두 지정가 매수 주문 후보가 된다.
- 빈 슬롯은 `previous_price < buy_price <= current_price` 인 empty 슬롯이 한 평가 사이클 동안 정확히 1개일 때만 `ord_type=price` 시장가 예산매수를 낸다.
- 한 평가 사이클 안에 여러 `buy_price`를 동시에 위로 돌파하면 그 상승 구간 매수는 건너뛴다.
- 보유 슬롯은 현재가가 `sell_price` 이상이면 바로 매도 후보가 된다.
- 매수 주문은 접수 시점이 아니라 `GET /v1/order` 재조회에서 `state=done`으로 확인될 때만 해당 슬롯의 `held_qty`에 반영된다.

### 주문 옵션 주의사항

- `post_only`는 지정가 주문(`ord_type=limit`)에서만 사용 가능하다.
- `post_only`는 `smp_type`과 함께 사용할 수 없다.
- `best` 주문은 `time_in_force`(`ioc` 또는 `fok`)가 필수다.
- `identifier`는 계정 전체 주문 기준으로 유일해야 하며, 한번 사용한 값은 재사용하지 않는 편이 안전하다.
- `smp_type` 사용 시 응답에 `prevented_volume`, `prevented_locked` 필드가 추가된다.

### 자산 잠금

- 매수 주문 생성 시 호가 자산(KRW)이 잠긴다.
- 매도 주문 생성 시 기준 자산(BTC)이 잠긴다.
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
- 선택 기능: Private WebSocket `myOrder` 캐시
- 권한: `주문조회`
- `uuid` 또는 `identifier` 중 하나가 필요하다.
- 주요 응답 필드:
  - `state`: `wait`(대기), `watch`(예약), `done`(체결 완료), `cancel`(취소)
  - `executed_volume`: 실제 체결된 수량
  - `remaining_volume`: 미체결 잔여 수량
  - `trades`: 부분 체결 내역 배열
  - `smp_type`, `prevented_volume`, `prevented_locked`: SMP 관련 (해당 주문만)

### 개별 주문 취소

- `DELETE /v1/order`
- 권한: `주문하기`
- `uuid` 또는 `identifier` 중 하나가 필요하다.

현재 코드 연결:

- 조회는 `app/exchange/crypto.py::get_order_status`에서 사용한다.
- terminal 주문 이벤트 캐시는 `app/exchange/upbit_ws.py::UpbitOrderWebSocketCache`에서 관리한다.
- 취소는 `app/exchange/crypto.py::cancel_order`에서 사용한다.

주의:

- `UPBIT_WS_ORDER_ENABLED=false` 가 기본값이며, 기본 동작은 기존 REST `/v1/order` 조회와 같다.
- 인증 WebSocket 엔드포인트는 `wss://api.upbit.com/websocket/v1/private` 이며, 기존 JWT 인증 헤더 생성 로직을 사용한다.
- `myOrder` 구독 메시지는 설정된 `SYMBOL`을 대문자 `codes`로 제한한다. 예: `codes=["KRW-BTC"]`.
- 캐시는 `uuid`, `state`, `executed_volume`, `remaining_volume`을 파싱한다. 기본 payload와 JSON list wrapper를 허용하며 단순 키(`uid`, `s`, `ev`, `rv`, `cd`, `ty`)도 처리한다.
- `get_order_status(order_id)`는 캐시 상태가 `done` 또는 `cancel`일 때만 REST를 생략한다.
- `wait`, `watch`, `trade`, `prevented`, 첫 이벤트 없음, stale event, 연결 오류, 의존성 누락, 인증 실패, 잘못된 심볼/type/payload는 모두 REST `/v1/order` fallback 으로 처리한다.
- 캐시 miss 이후 REST 오류는 기존처럼 호출자에게 전파한다. pending-order 상태 적용 로직은 WebSocket 이벤트로 바꾸지 않는다.

## 체결 대기 주문 조회

- `GET /v1/orders/open`
- 권한: `주문조회`
- 미체결 주문 목록을 확인할 때 사용한다.

주요 파라미터:

- `market`: 마켓 필터 (선택)
- `state`: `wait`(지정가 대기) 또는 `watch`(예약가 대기), 기본값 `wait`
- `states[]`: 여러 상태 동시 조회 시 배열로 전달 — `state`와 동시 사용 불가
- `limit`: 조회 건수 (기본 100)
- `order_by`: 정렬 (`asc` / `desc`, 기본 `desc`)

운영상 유용한 시점:

- 재시작 직후 미체결 주문 동기화
- 중복 주문 방지
- 장시간 대기 주문 정리

## 종료 주문 목록 조회

- `GET /v1/orders/closed`
- 권한: `주문조회`
- 전량 체결 완료 및 취소된 주문 목록을 조회한다.

주요 파라미터:

- `market`: 마켓 코드 (필수)
- `state` / `states[]`: `done`(체결), `cancel`(취소), 기본값 `done,cancel` — 둘 중 하나만 사용
- `start_time` / `end_time`: 조회 기간 (최대 7일 구간)
- `limit`: 조회 건수 (기본 100)
- `order_by`: 정렬 (`asc` / `desc`)

운영상 유용한 시점:

- 체결 이력 확인 및 PostgreSQL 상태와 대조
- 누락된 체결 복구 검증

## 취소 후 재주문

- `POST /v1/orders/cancel_and_new`
- 권한: `주문하기`
- 기존 주문 취소와 신규 주문 생성을 원자적으로 실행한다. 취소가 완료돼야 신규 주문이 생성된다.

주요 파라미터:

- `prev_order_uuid` 또는 `prev_order_identifier`: 취소 대상 주문 식별자 (필수, 둘 중 하나)
- `new_ord_type`: 신규 주문 유형 (필수)
- `new_volume`: 신규 주문 수량. `"remain_only"` 입력 시 기존 주문의 미체결 잔량 자동 적용
- `new_price`: 신규 주문 단가/금액
- `new_time_in_force`: `ioc`, `fok`, `post_only`
- `new_smp_type`: `cancel_maker`, `cancel_taker`, `reduce`
- `new_identifier`: 신규 주문 식별자 (취소된 identifier 재사용 불가)

제약사항:

- 신규 주문은 기존과 동일한 페어, 동일한 주문 방향만 가능하다.

## 요청 수 제한

모든 요청 수 제한은 초 단위다. 같은 Rate Limit 그룹에 속한 API끼리는 허용량을 함께 공유한다.

### REST API

| 그룹 | 포함 API 예시 | 제한 | 단위 |
| --- | --- | --- | --- |
| **ticker** (Quotation) | `GET /v1/ticker` | 초당 10회 | IP |
| **default** (Exchange) | `GET /v1/accounts`, `GET /v1/order`, `DELETE /v1/order`, `GET /v1/orders/open`, `GET /v1/orders/chance` 등 | 초당 30회 | 계정 |
| **order** | `POST /v1/orders`, `POST /v1/orders/cancel_and_new` | 초당 8회 | 계정 |
| **order-test** | `POST /v1/orders/test` | 초당 8회 | 계정 |
| **order-cancel-all** | `DELETE /v1/orders` (일괄 취소) | 2초당 1회 | 계정 |

### WebSocket

| 요청 유형 | 제한 | 단위 |
| --- | --- | --- |
| 연결 요청 | 초당 5회 | IP(공개) / 계정(인증) |
| 데이터 요청 | 초당 5회, 분당 100회 | IP(공개) / 계정(인증) |

### 특수 정책

- **Origin 헤더 포함 요청**: Quotation API 및 WebSocket에서 10초당 1회로 별도 제한된다.
- `429 Too Many Requests`가 오면 즉시 같은 그룹 호출을 멈추고 대기한다.
- 반복 초과는 `418` 상태코드 반환 후 임시 또는 영구 제한으로 이어질 수 있으므로, 단순 재시도 루프를 만들지 않는다.
- 응답 헤더 `Remaining-Req`를 보고 조절하는 것이 권장된다.

## KRW 마켓 운영 메모

### 최소 주문 금액

- KRW 마켓 최소 주문 가능 금액: **5,000 KRW**

### 가격 단위 (호가 단위)

지정가 주문 시 가격을 아래 단위에 맞게 보정해야 한다. 단위에 맞지 않으면 주문이 거부된다.

| 가격 구간 (KRW) | 호가 단위 |
| --- | --- |
| 2,000,000 이상 | 1,000 |
| 1,000,000 ~ 2,000,000 미만 | 1,000 |
| 500,000 ~ 1,000,000 미만 | 500 |
| 100,000 ~ 500,000 미만 | 100 |
| 50,000 ~ 100,000 미만 | 50 |
| 10,000 ~ 50,000 미만 | 10 |
| 5,000 ~ 10,000 미만 | 5 |
| 1,000 ~ 5,000 미만 | 1 |
| 100 ~ 1,000 미만 | 1 |

BTC 현재가가 1억원 수준이면 **1,000원 단위**가 적용된다. 그리드 전략에서 `buy_price`, `sell_price`를 생성할 때 반드시 이 단위로 절사/반올림해야 한다.

### 기타 운영 주의

- 이 값은 가격대와 마켓 정책에 따라 달라질 수 있으므로, 고정 숫자를 코드에 박아두기보다 공식 문서와 `orders/chance`를 함께 확인하는 편이 안전하다.

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

- `app/exchange/crypto.py`에 `orders/chance` 연동 추가
- 실주문 전 `orders/test` 사전 검증 추가
- `Remaining-Req` 파싱 및 throttling 추가
- 미체결 주문 조회(`orders/open`)를 통한 재시작 복구 로직 보강
- 가격 단위/최소 주문 금액을 KRW 마켓 정책 기준으로 정규화하는 유틸 추가
- 현재가 WebSocket ticker 이벤트 기반 메인 루프 추가: 최소 3초 throttle, 5초 REST fallback
- `smp_type` 옵션 도입 검토 (자전거래 방지)
- `post_only` 옵션 도입 검토 (수수료 최적화)
- WebSocket MyOrder 캐시 확대 검토 — 현재는 terminal 상태의 보수적 조회 가속에만 사용
- `orders/closed`를 활용한 재시작 후 체결 이력 대조 로직 추가
- `orders/cancel_and_new`의 `remain_only` 옵션을 이용한 지정가 재배치 로직 검토

## 문서 갱신 방법

문서가 바뀌었는지 확인할 때는 다음 순서로 보면 된다.

1. `https://docs.upbit.com/kr/llms.txt`
2. 인증 / REST API 가이드 / Rate Limits
3. 현재 저장소가 실제로 호출하는 엔드포인트 문서
4. 주문 관련 changelog 또는 revision history

이 문서를 갱신할 때는 날짜를 함께 바꾼다.
