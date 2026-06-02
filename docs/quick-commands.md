# auto 빠른 명령어 모음 (Cheat Sheet)

[auto](..) 자동매매 봇의 운영 중 자주 사용되는 핵심 명령어들을 신속하게 복사 및 실행하기 위한 치트 시트입니다.

---

## 📌 기준 위치 & 환경 요약

### 📂 작업 디렉터리 이동
- **로컬 개발 환경**: `cd /home/yangyag/auto`
- **EC2 운영 환경**: `cd /home/ubuntu/auto`

### ⚙ 봇 주요 상태 제어
- **실행**: `./run.sh`
- **종료**: `./stop.sh`
- **재시작**: `./stop.sh && ./run.sh`

### 📜 로그 및 모니터링
- **오늘 로그 실시간 조회**: `tail -f logs/trading-$(date +%F).log`
- **최신 로그 추적 스크립트**: `./tail-latest-log.sh`
- **날짜별 최저가 점검**: `python3 scripts/check_daily_low.py`

### 🛠 그리드 도구
- **그리드 반영**: `python3 scripts/apply_grid_properties_to_postgres.py --force`
- **그리드 상태**: `python3 scripts/show_grid_state.py`
- **설정 파일**: [grid.properties](../grid.properties)

---

## ⭐️ 제일 자주 쓰는 필수 명령 4선

실제 운용 과정에서 사용 빈도가 가장 높은 핵심 명령 세트입니다.

### 1. `[grid]` 그리드 반영
`grid.properties` 파일에 기재된 값을 기준으로 데이터베이스 그리드 구성을 강제 반영 및 갱신합니다.
```bash
python3 scripts/apply_grid_properties_to_postgres.py --force
```

### 2. `[state]` 현재 상태 보기
현재 데이터베이스에 로드되어 있는 슬롯별 상태, 보유 재고 및 계획 매수 금액 요약을 출력합니다.
```bash
python3 scripts/show_grid_state.py
```

### 3. `[log]` 실시간 로그 확인
오늘 날짜(`$(date +%F)`) 기준으로 기록 중인 봇의 운영 로그 끝부분을 실시간으로 추적합니다.
```bash
tail -f logs/trading-$(date +%F).log
```

### 4. `[bot]` 봇 안전 재시작
백그라운드에서 구동 중인 봇을 안전하게 정지시킨 후 즉시 재차 구동합니다.
```bash
./stop.sh && ./run.sh
```

---

## 1. 봇 프로세스 제어

### `[run]` 백그라운드 실행
봇 프로세스를 백그라운드 모드로 구동합니다.
```bash
./run.sh
```

### `[stop]` 프로세스 정지
가동 중인 백그라운드 봇을 안전하게 정지시킵니다.
```bash
./stop.sh
```

### `[check]` 구동 상태 점검
기록된 PID 파일 검증 및 실제 실행 중인 파이썬 프로세스 목록을 확인합니다.
```bash
test -f .auto-trading.pid && cat .auto-trading.pid || true
ps -eo pid,args | grep '[p]ython.*/auto/main.py'
```

---

## 2. 로그 모니터링

### `[tail]` 오늘 로그 마지막 50줄 출력
오늘 날짜의 로그 파일에서 최근 기록된 50줄을 출력합니다.
```bash
tail -n 50 logs/trading-$(date +%F).log
```

### `[follow]` 실시간 로그 추적
로그 파일의 끝부분에 붙어 신규 기록 내용을 실시간 모니터링합니다.
```bash
tail -f logs/trading-$(date +%F).log
```

### `[latest]` 최신 로그 자동 추적
수동 날짜 입력 없이 자동으로 최신 로그 파일을 감지해 실시간 조회합니다.
```bash
./tail-latest-log.sh
```

### `[scan]` 날짜별 최저 시세 분석
과거 로그들을 스캔하여 일자별 최저 도달 현재가를 요약 출력합니다. (매수 임계점 근접 여부 판정용)
*(EC2 환경에서는 가상환경 파이썬 호출 권장)*
```bash
python3 scripts/check_daily_low.py
```

---

## 3. 업비트 계정 잔고 확인

### `[balance]` 가용 원화(KRW) 잔고 1회 조회
API를 통해 거래소에 대기 중인 주문 가능한 KRW 잔액을 즉시 출력합니다.
```bash
python3 main.py balance
```

> [!WARNING]
> **평균매수가 기준 자산 평가 착시**: 
> `main.py balance`는 단순 가용 KRW 잔고만 반환합니다. 업비트에서 계산하여 노출하는 `평균매수단가 * 보유수량` 자산액은 계정의 총 합산 평균단가이므로, 봇이 관리하는 개별 그리드 슬롯의 독립 매수원가 잔액들과 일치하지 않을 수 있습니다. 봇의 실제 슬롯 원장 기준 종합 평가는 다음 `자산 확인` 스크립트를 통해 검증하십시오.

---

## 4. 봇 원장 기준 실제 자산 확인

업비트 계정의 총 잔고와 봇의 가격 슬롯별 잔여 BUY 매수원가를 크로스 매칭하여 종합 자산 명세를 보여주는 Read-Only 분석 도구입니다.

### `[assets]` 최근 120일 내역 기준 조회
```bash
scripts/upbit_actual_assets.py
```

### `[lookback]` 분석 기간 확장 조회
수량 불일치 경고가 뜨거나 장기 보유 자산이 누락된 경우 조회 윈도우를 늘려 검증합니다.
```bash
scripts/upbit_actual_assets.py --lookback-days 180
```

> [!NOTE]
> 출력값 중 `KRW + 봇 슬롯별 잔여 매수원가`는 봇의 독립적인 매수 원장 기준 누적 금액이고, `KRW + 현재 평가액`은 실시간 시세 기준 자산 평가 금액입니다.

---

## 5. 미체결 매도 대기 실시간 현황

현재 걸려 있는 모든 매도 주문을 봇의 가격 슬롯별 실제 취득 단가와 1:1 FIFO 매칭하여, 현재 시가 기준 각 슬롯별 상세 미실현 손익 구조를 시각화합니다. 기본 마켓은 현재 환경의 `SYMBOL`이며, 수량 라벨은 해당 마켓의 기초자산(`KRW-USDT`이면 `USDT`)으로 표시됩니다.

### `[monitor]` 기본 모니터링 구동
```bash
.venv/bin/python scripts/upbit_open_sell_monitor.py
```

### `[btc]` 과거 KRW-BTC 라이브 장부 명시 조회
```bash
.venv/bin/python scripts/upbit_open_sell_monitor.py --market KRW-BTC --bot-key krw-btc-live
```

### `[lookback]` 주문 내역 조회 기간 확장
오래전에 매수된 후 대기 중인 슬롯의 매수 가격이 매치되지 않을 때 조회 범위를 연장합니다.
```bash
.venv/bin/python scripts/upbit_open_sell_monitor.py --lookback-days 180
```

> [!TIP]
> **웹(Web) 및 API 확인**: 
> 본 정보는 아래의 비 CLI 경로를 통해서도 동일하게 실시간 모니터링할 수 있습니다:
> - **브라우저 전용 콘솔**: `http://<EC2_IP>:8086/ops` 접속 후 -> `매도 대기` 버튼 클릭
> - **모바일 API**: JWT 토큰 인증 후 `GET /v1/monitor/open-sells` 엔드포인트 호출 ([mobile-api.md](../docs/mobile-api.md) 참조)

---

## 6. 그리드 DB 강제 반영

`grid.properties` 파일 설정을 파싱하여 데이터베이스 그리드 정보를 새로 구성합니다.

### `[apply]` 기본 properties 파일 사용
```bash
python3 scripts/apply_grid_properties_to_postgres.py --force
```

### `[custom]` 특정 properties 파일 수동 지정
```bash
python3 scripts/apply_grid_properties_to_postgres.py --properties-file my-grid.properties --force
```

> [!CAUTION]
> `--force` 매개변수는 기존에 기록되어 구동 중이던 모든 슬롯 이력과 매수 재고 상태를 DB에서 강제로 날리고 **완전히 새로 빌드**하므로 가동 중인 봇을 멈추고 각별한 주의하에 실행하십시오.

---

## 7. 실시간 그리드 슬롯 상세 요약

### `[state]` 그리드 상태 요약 출력
현재 DB 상의 슬롯 번호별 `buy/held/sell/planned/status` 명세와 총보유 재고량, 구간 예산 점유율 등을 한눈에 확인합니다.
```bash
python3 scripts/show_grid_state.py
```

---

## 8. 실현 손익 정밀 계산 (현재 SYMBOL)

업비트 API 주문 기록을 바탕으로 봇 전용 주문 식별자(`identifier`)를 추적해 수수료 차감 후 순 손익을 FIFO(선입선출) 방식으로 계산합니다. 기본 마켓은 현재 환경의 `SYMBOL`이며, 수량 라벨은 해당 마켓의 기초자산(`KRW-USDT`이면 `USDT`)으로 표시됩니다.

### `[all]` 최근 90일 요약 조회
최근 90일 치 기록을 일/주/월/년/전체 단위 버킷으로 자동 매칭하여 종합 출력합니다.
```bash
.venv/bin/python scripts/upbit_realized_pnl.py
```

### `[d]` 오늘 당일 수익 조회
```bash
.venv/bin/python scripts/upbit_realized_pnl.py --period d
```

### `[w]` 이번 주 누적 수익 조회 (월요일~오늘)
```bash
.venv/bin/python scripts/upbit_realized_pnl.py --period w
```

### `[m]` 이번 달 누적 수익 조회 (1일~오늘)
```bash
.venv/bin/python scripts/upbit_realized_pnl.py --period m
```

### `[range]` 특정 기간 수동 조회 & 조회 마진 확장
```bash
.venv/bin/python scripts/upbit_realized_pnl.py --from 2026-05-01 --to 2026-05-31 --lookback 45
```

### `[btc]` 과거 KRW-BTC 라이브 장부 명시 조회
```bash
STATE_BOT_KEY=krw-btc-live .venv/bin/python scripts/upbit_realized_pnl.py --market KRW-BTC
```

> [!WARNING]
> **lookback 부족 위험 경고**: 
> 계산 시작일 이전에 완료된 과거 매수 건을 매칭해야 하므로 `--lookback` 일수를 넉넉히 주어야 정확합니다. 경계선 부근에서 매수 기록이 검출되어 경고 메시지가 발생할 경우 lookback 일수를 늘려 다시 실행하십시오.

### 슬롯별 실현손익 (`upbit_pnl_by_slot.py`)
어떤 그리드(슬롯)를 팔아 생긴 실현손익인지 슬롯 단위로 본다. `upbit_realized_pnl.py` 와 같은 슬롯 1:1 FIFO 매칭 결과를 슬롯별로 묶어 `[ 슬롯별 실현손익 ]`(슬롯·그리드매수가(참고)·매도주문수·실현손익(KRW)·매도수량 + 합계행)과 `[ 매도별 상세 ]`(체결시각KST·슬롯·매도수량·실현손익·sell_uuid) 2개 섹션을 출력한다. 인자 의미(`--period d/w/m/y`, `--from/--to`, `--market`, `--lookback`, `--reset-sell-uuid`)는 `upbit_realized_pnl.py` 와 동일하다.

```bash
# 오늘 슬롯별 실현손익
.venv/bin/python scripts/upbit_pnl_by_slot.py --period d

# 이번 달 슬롯별 실현손익
.venv/bin/python scripts/upbit_pnl_by_slot.py --period m

# 특정 기간 + lookback 마진 확장
.venv/bin/python scripts/upbit_pnl_by_slot.py --from 2026-05-01 --to 2026-05-31 --lookback 45

# 과거 KRW-BTC 라이브 장부 명시 조회
STATE_BOT_KEY=krw-btc-live .venv/bin/python scripts/upbit_pnl_by_slot.py --market KRW-BTC
```

> [!NOTE]
> **그리드매수가는 참고가**: `그리드매수가` 컬럼은 **현재 PostgreSQL 그리드 상태 기준 참고가**이며, 현재 그리드 스냅샷(`load_grid_snapshot`)에서 슬롯 가격을 끌어온다. 리센터링 이력이 있으면 과거 매도 당시의 슬롯 가격과 다를 수 있으나, 실현손익 숫자 자체는 실제 체결 FIFO 매칭 기반이라 정확하며 이 참고가에 영향받지 않는다. DB 미연결/빈 스냅샷이면 해당 컬럼을 `-` 로 두고 정상 진행한다.

---

## 9. 손절(Stop-Loss) 관련 명령

### `[L1]` LEVEL 1 손절 락 해제
L1 단계 손절이 작동해 매수가 잠겼을 때, 매수 재개를 위해 락 상태를 안전하게 해제합니다.

- **기본 활성화 가상환경 호출**:
  ```bash
  python3 main.py reset-stop-loss
  ```
- **EC2 venv 활성화 생략 절대 경로 호출**:
  ```bash
  /home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py reset-stop-loss
  ```

### `[L2]` LEVEL 2 재시작 잠금 강제 우회
L2 단계 전량 청산 후 적용되는 24시간 쿨다운 필터를 수동 강제 우회합니다.
```bash
python3 main.py reset-stop-loss --force
```

### `[status]` 실시간 손절 상태 모니터링
손절/브레이크아웃 가드 적용 여부는 모바일 API 봇 상태 엔드포인트로 확인합니다. (`show_grid_state.py`는 손절 플래그를 출력하지 않습니다.)
```bash
curl -s http://127.0.0.1:8086/v1/bot/status \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```
> 상세 인증 및 응답 필드는 [mobile-api.md](../docs/mobile-api.md)의 `GET /v1/bot/status` 항목을 참조하십시오.

---

## 10. 테스트 검증 명령

### `[all]` 전체 단위 테스트 구동
```bash
python3 -m unittest discover -s tests -v
```

### `[props]` 그리드 설정 모듈 타깃 테스트
```bash
python3 -m unittest tests.test_grid_properties tests.test_apply_grid_properties_script -v
```

### `[pg]` PostgreSQL 레포지토리 연동 테스트
```bash
python3 -m unittest tests.test_postgres_grid_repository tests.test_postgres_order_repository tests.test_postgres_runtime_lock -v
```

---

## 11. 환경 변수 및 설정 크로스 체크

### DB 가동 정보 검증
```bash
python3 - <<'PY'
import app.config.settings as cfg
print(f"STATE_BOT_KEY: {cfg.STATE_BOT_KEY}")
print(f"HOST: {cfg.PGHOST} | PORT: {cfg.PGPORT} | DB: {cfg.PGDATABASE} | USER: {cfg.PGUSER} | SCHEMA: {cfg.PGSCHEMA}")
PY
```

### 실시간 가격 수신 모드 검증
```bash
python3 - <<'PY'
import app.config.settings as cfg
print(f"WebSocket Public Enabled: {cfg.UPBIT_WS_PUBLIC_ENABLED}")
print(f"Event Loop Enabled: {cfg.UPBIT_WS_EVENT_LOOP_ENABLED}")
print(f"WS Event Min Interval: {cfg.UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS}s")
print(f"REST Poll Interval (Fallback): {cfg.PRICE_POLL_INTERVAL}s")
PY
```

---

## 12. 환경 설정 파일 구성 가이드

### [grid.properties](../grid.properties) 설정 템플릿
```properties
MIN_BUY_PRICE=1430
MAX_BUY_PRICE=1530
TOTAL_BUDGET_KRW=10000000
GRID_STEP_PCT=0.2
TP_MODEL=k
TP_K_BASE=3.2
TP_K_FLOOR=3.0
```
> 위 값은 현재 `cfg.SYMBOL`(KRW-USDT) 기준 예시이며, 실제 운영값은 [grid.properties](../grid.properties)를 직접 확인하십시오.

---

## 13. 라이브 리셋 및 갱신 (현재 SYMBOL)

보유 자산을 즉시 현금화(시장가 전량 청산)하고, 봇 정지 및 그리드 신규 구조 재반영 작업을 단일 트랜잭션으로 진행합니다.

### `[reset]` 전량 청산 및 그리드 리빌드 원스톱 실행
```bash
.venv/bin/python scripts/reset_live.py
```

> [!IMPORTANT]
> 리셋 스크립트는 봇 프로세스를 안전하게 종료하고 청산과 DB 반영까지 수행하지만, **봇을 자동으로 재시작하지는 않습니다.** 결과를 면밀히 확인한 뒤 직접 아래 명령어로 수동 구동해주십시오.
> ```bash
> ./run.sh
> ```
