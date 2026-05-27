# 운영 / 인프라 가이드

auto 자동매매 봇의 EC2 운영, 배포, 점검, 손절 절차 한곳에서 보기

📦 main 브랜치
🖥 EC2 43.202.113.123
🐍 .venv/bin/python
📂 /home/ubuntu/auto

🖥EC2 서버

IP
:   43.202.113.123

User
:   ubuntu

Key
:   /home/yangyag/auto/aws/test-keypair.pem

경로
:   /home/ubuntu/auto

⚙봇 런타임

Python
:   .venv/bin/python

Entry
:   main.py

.env
:   /home/ubuntu/auto/.env

로그
:   logs/trading-YYYY-MM-DD.log

🚀핵심 스크립트

시작
:   ./run.sh

종료
:   ./stop.sh

로그
:   ./tail-latest-log.sh

점검
:   scripts/check\_daily\_low.py

🔁Git 원격

로컬
:   git@github.com:yangyag/auto.git

EC2
:   https://github.com/yangyag/auto.git

브랜치
:   main

## 문서 역할

- 이 문서는 이 저장소의 **인프라, 운영, 배포 기준**만 다룬다.
- 프로그램 로직과 전략 설명은 `README.md`를 본다.
- 처음 설치 절차는 `setup.html`를 본다.

## 로컬 / EC2 고정 정보

| 항목 | 로컬 | EC2 |
| --- | --- | --- |
| 작업 디렉터리 | `/home/yangyag/auto` | `/home/ubuntu/auto` |
| Git 원격 | `git@github.com:yangyag/auto.git` | `https://github.com/yangyag/auto.git` |
| 기본 브랜치 | `main` | `main` |
| .env 경로 | `./.env` | `/home/ubuntu/auto/.env` |
| 가상환경 Python | `.venv/bin/python` | `/home/ubuntu/auto/.venv/bin/python` |
| 봇 프로세스 패턴 | — | `.venv/bin/python /home/ubuntu/auto/main.py` |
| SSH 키 | `/home/yangyag/auto/aws/test-keypair.pem` | — |
| SSH 사용자 | — | `ubuntu` |
| 서버 IP | — | `43.202.113.123` |

⚠ 혼동 주의

EC2의 `/home/ubuntu/llm.env` 는 다른 서비스용 파일이다. 자동매매 저장소 설정 파일로 착각하면 안 된다.

## 운영 관련 파일

| 파일 | 용도 |
| --- | --- |
| `docs/setup.md` | git clone 직후 설치 · 초기 설정 · 첫 실행 준비 |
| `README.md` | 프로그램 로직과 전략 설명 |
| `docs/quick-commands.md` | 자주 쓰는 운영 명령 모음 |
| `.env_sample` | 로컬 `.env` 작성 기준 |
| `run.sh` | 백그라운드 실행 |
| `stop.sh` | 백그라운드 종료 |
| `tail-latest-log.sh` | 최신 날짜 로그 추적 |
| `logs/trading-YYYY-MM-DD.log` | 운영 로그 |

## EC2 접속

기본 SSH 절차:

bash

```
chmod 600 /home/yangyag/auto/aws/test-keypair.pem
ssh -o StrictHostKeyChecking=no -i /home/yangyag/auto/aws/test-keypair.pem ubuntu@43.202.113.123
```

EC2에 붙은 뒤 기본 위치:

bash

```
cd /home/ubuntu/auto
```

## Git / 배포 기준

📝 커밋 메시지

사용자가 다른 언어를 명시하지 않는 한 **한국어**를 우선한다.

### EC2에서 먼저 확인할 것

bash

```
git branch -vv
git status --short
test -f /home/ubuntu/auto/.env && echo env:present
ps -eo pid,args | grep '[p]ython /home/ubuntu/auto/main.py' \
  || ps -eo pid,args | grep '[p]ython3 /home/ubuntu/auto/main.py' \
  || ps -eo pid,args | grep '[p].venv/bin/python /home/ubuntu/auto/main.py'
```

### EC2 최신 커밋 반영 절차

1. `cd /home/ubuntu/auto`
2. `./stop.sh` 로 봇 정지
3. `git fetch origin`
4. `git status --short` 로 tracked 변경 확인
5. 필요 시 정리 후 `git pull --ff-only origin main`
6. `.venv/bin/python -c "import main"` 으로 venv 무결성 확인
7. `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh`
8. `./tail-latest-log.sh` 또는 `tail -n 50 logs/trading-$(date +%F).log`

🚫 절대 금지

EC2에 `.venv/`, export 결과 파일, 보조 스크립트 같은 untracked 파일이 남아 있을 수 있다. **`git clean -fd` 같은 파괴적 정리는 확인 없이 절대 실행하지 않는다.**

pull 이 tracked 변경과 충돌하면 무작정 되돌리지 말고 어떤 파일인지 먼저 확인한다.

## Python 실행 환경

### EC2

- EC2에는 `/home/ubuntu/auto/.venv` 가 이미 구성되어 있다. **새로 만들지 말고 기존 venv 를 그대로 사용한다.**
- 쉘에서 직접 작업할 때는 activate 스크립트로 활성화한다.

bash

```
source /home/ubuntu/auto/.venv/bin/activate
```

- 배포 스크립트나 원격 명령처럼 activate 없이 실행할 때는 `.venv/bin/python` 절대 경로를 직접 호출한다.
- `run.sh` 도 `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh` 형태로 넘긴다.
- `requirements.txt` 변경 시에도 `.venv` 를 재생성하지 말고 기존 venv 에 설치만 추가한다.

bash

```
/home/ubuntu/auto/.venv/bin/python -m pip install -r requirements.txt
```

⚠ venv 보호

`.venv/` 는 git untracked 상태가 정상이다. `git clean -fd` 같은 파괴적 정리 대상에서 반드시 제외한다.

venv 가 깨졌다고 판단되면 재생성 전에 먼저 `/home/ubuntu/auto/.venv/bin/python -c "import main"` 으로 실패 원인을 확인한다. import 가 되면 venv 자체 문제가 아니라 설정/의존성 문제일 가능성이 높다.

### 로컬

- 이 작업 디렉터리는 시스템 `python3 -m venv .venv` 가 `ensurepip` 부재로 실패할 수 있다.
- 같은 문제가 다시 나오면 우선 `uv`로 가상환경을 만든다.

bash

```
~/.local/bin/uv venv --clear .venv
~/.local/bin/uv pip install --python .venv/bin/python pip
```

이후 의존성 설치와 검증은 가능하면 `.venv/bin/python` 기준으로 실행한다.

bash

```
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "import main"
.venv/bin/python -m unittest discover -s tests -v
```

## 운영 점검 기준

- `.env`가 없다고 가정하지 말고 먼저 `/home/ubuntu/auto/.env` 존재 여부를 확인한다.
- EC2에서 프로세스를 찾을 때 `python3 /home/ubuntu/auto/main.py`만 보지 말고 실제 경로인 `/home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py` 패턴도 함께 본다.
- 백그라운드 실행/종료는 가능하면 `./run.sh`, `./stop.sh`를 우선 사용한다.
- 직접 `nohup python3 main.py`를 실행하면 PID 추적과 로그 해석이 꼬일 수 있다.
- 운영 로그는 `logs/trading-YYYY-MM-DD.log`를 기준으로 본다.
- 날짜별 최저 현재가는 `scripts/check_daily_low.py` 로 빠르게 확인할 수 있다 (매수 라인 도달 여부 점검용).
- 매도 대기 주문의 슬롯별 미실현 손익은 `.venv/bin/python scripts/upbit_open_sell_monitor.py` 로 확인한다. 업비트 평균매수가 기준과 달리 각 슬롯의 실제 매수원가 대비 손익을 보여준다.
- 테스트 로그가 같은 날짜 파일에 남을 수 있으므로 로거 이름 `__main__` / `main` 도 함께 확인한다.

⚠ 실거래 주의

실거래 주문이 발생할 수 있는 루프 실행은 **명시적으로 필요할 때만** 한다.

## 주문 관련 용어

📌 quantity vs held\_qty

`orders` 테이블의 `quantity` 컬럼은 **최초 발주량**이다. 부분 체결 시 실제 체결량과 다를 수 있으므로 실 체결량은 `GridState.held_qty` 를 참조한다. 사고 분석 시 두 값을 함께 본다.

## 라이브 예산 조정 주의

💰 adjust\_budget\_live.py

`scripts/adjust_budget_live.py` 는 **절대 총예산**(`--target-budget`)으로 운영되며, 현재 그리드의 가격 구조와 보유 수량을 유지한 채 **계획 수량만 재계산**한다.

## 자격증명 / 민감정보 원칙

🔐 보안 규칙

- API 키는 환경변수 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` 로만 주입한다.
- PostgreSQL 접속정보도 프로젝트 루트 `.env` 또는 EC2 `/home/ubuntu/auto/.env` 로만 관리한다.
- 민감정보를 문서, 샘플 파일, 커밋에 **복제하지 않는다**.

## 손절(Stop-Loss) 운영 가이드

손절 기능은 현재가가 그리드 최하단 아래로 내려갔을 때 단계별 자동 대응을 제공한다. 설정된 임계값에 도달하고 컨펌 조건이 만족되면 자동으로 포지션을 청산한다. 자세한 설계와 이론은 [docs/stop-loss-design.md](stop-loss-design.md) 를 참조한다.

### 손절 모드 활성화

`grid.properties` 또는 환경변수로 제어된다. 기본값은 `band_multiple` 모드:

properties

```
# 모드: band_multiple (권장) | fixed_pct | off
STOP_LOSS_MODE=band_multiple

# band_multiple 모드: 그리드 폭 배수 기반 임계값 (권장)
STOP_LOSS_BAND_MULTIPLE=1.5        # k값, 범위 1.0~2.0

# fixed_pct 모드: 고정 퍼센트 기반 (백테스트/비교용)
STOP_LOSS_L0_PCT=10
STOP_LOSS_L1_PCT=20
STOP_LOSS_L2_PCT=30
```

### L0 / L1 / L2 트리거 시 봇 거동

LEVEL 0 · 경계

L0

현재가 < L0 임계값 (기본 −10%)

신규 매수만 차단. 손절 본 흐름은 실행하지 않음. 기존 TP 매도는 정상 진행. **가역적**.
**재개:** 현재가가 L0 위로 회복하면 자동 해제.

LEVEL 1 · 부분 청산

L1

현재가 < L1 임계값 (기본 −20%)

컨펌 후 **1시간 대기**하여 보유 BTC **50%**를 threshold 가격 지정가 매도. 매수 영구 차단.
**재개:** `reset-stop-loss` CLI. lockout 미경과면 exit 2.

LEVEL 2 · 전량 청산

L2

현재가 < L2 임계값 (기본 −30%)

컨펌 후 **30분 대기**하여 잔여 100%를 시장가로 **분할 청산**. 봇 즉시 종료. 24시간 재시작 잠금.
**재개:** 새 그리드로 `init-grid --force` 재구성.

### ENV 파라미터

| 파라미터 | 기본값 | 의미 | 권장 범위 | 설명 |
| --- | --- | --- | --- | --- |
| `STOP_LOSS_MODE` | `band_multiple` | 손절 모드 | `band_multiple` / `fixed_pct` / `off` | band\_multiple 권장 |
| `STOP_LOSS_BAND_MULTIPLE` | `1.5` | 그리드 폭 배수 | 1.0 ~ 2.0 | 임계값 = min × (1 − k × band\_ratio) |
| `STOP_LOSS_L0_PCT` | `10` | L0 고정 % | 5 ~ 15 | band\_multiple 모드에서 미사용 |
| `STOP_LOSS_L1_PCT` | `20` | L1 고정 % | 15 ~ 25 | band\_multiple 모드에서 미사용 |
| `STOP_LOSS_L2_PCT` | `30` | L2 고정 % | 25 ~ 35 | band\_multiple 모드에서 미사용 |
| `STOP_LOSS_CANDLE_UNIT` | `15` | 캔들 단위 (분) | 5 ~ 60 | 손절 트리거 컨펌용 캔들 종가 분석 |
| `STOP_LOSS_L0_CONSECUTIVE_CLOSES` | `4` | L0 연속 캔들 | 2 ~ 6 | 연속 종가가 임계 아래여야 트리거 |
| `STOP_LOSS_L1_CONSECUTIVE_CLOSES` | `4` | L1 연속 캔들 | 2 ~ 6 | — |
| `STOP_LOSS_L2_CONSECUTIVE_CLOSES` | `2` | L2 연속 캔들 | 1 ~ 4 | L2는 위험하므로 더 빠르게 컨펌 |
| `STOP_LOSS_L1_ARM_HOLD_SECONDS` | `3600` | L1 대기 (초) | 600 ~ 3600 | 컨펌 후 손절 실행까지 (1시간) |
| `STOP_LOSS_L2_ARM_HOLD_SECONDS` | `1800` | L2 대기 (초) | 300 ~ 1800 | 컨펌 후 손절 실행까지 (30분) |
| `STOP_LOSS_L1_LIQUIDATE_RATIO` | `0.5` | L1 청산 비율 | 0.3 ~ 0.7 | 0 = 0%, 1 = 100% |
| `STOP_LOSS_RESTART_LOCKOUT_HOURS` | `24` | L2 재시작 잠금 | 12 ~ 48 | L2 후 자동 재시작 금지 시간 |
| `STOP_LOSS_WEBHOOK_URL` | (없음) | 외부 알림 Webhook | URL | Slack/Generic Webhook |
| `STOP_LOSS_NOTIFICATION_ENABLED` | `True` | 외부 알림 활성화 | `True` / `False` | False면 URL 있어도 미발송 |

### reset-stop-loss CLI

L1 발동 후 매수 차단을 해제하거나 L2 24시간 잠금을 강제 해제하려면 `reset-stop-loss` 명령을 사용한다.

bash

```
# EC2에서 (venv 활성화 또는 절대 경로)
cd /home/ubuntu/auto
source .venv/bin/activate

# L1 해제
python main.py reset-stop-loss

# L2 24시간 잠금 강제 해제
python main.py reset-stop-loss --force

# 절대 경로:
/home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py reset-stop-loss [--force]
```

#### 역할

- **기본 (L1 해제):** 기존 포지션 상태 보존 / L1 매수 영구 차단 해제 / `stop_loss_active` false 복구
- **--force (L2 강제 해제):** `STOP_LOSS_RESTART_LOCKOUT_HOURS` 미경과 상태에서도 잠금 강제 해제. L2 후 새 그리드 없이 매수 재개 가능. 긴급용.
- **운영 로그:** `[STOP_LOSS] reset-stop-loss completed`

⚠ 주의

- `--force` 없이 lockout 미경과 상태에서 호출하면 **exit 2** 실패
- L2 이후는 포지션이 모두 청산되었으므로 `init-grid --force` 로 새 그리드를 생성해야 봇 재시작 가능
- `--force` 는 L2 강제 해제용 — L1 상태에서는 `--force` 없이 호출 권장

### L2 후 재시작 절차

L2 손절이 발동되면:

1. 봇이 자동으로 종료된다 (프로세스 exit, 메인 루프 탈출)
2. 모든 포지션이 청산된다 (시장가 분할 매도)
3. `liquidated_at` 타임스탬프가 DB에 기록된다
4. 24시간 동안 자동 재시작이 차단된다
5. 손절 상태(`stop_loss_armed_at`, `stop_loss_active` 등)는 DB에 영속화되어 재시작 후 복원

재시작 방법:

bash

```
cd /home/ubuntu/auto
./stop.sh
git fetch origin && git pull --ff-only origin main  # 필요시 코드 동기화
.venv/bin/python main.py init-grid --force            # 새 그리드 생성 (기존 상태 초기화)
PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh
./tail-latest-log.sh
```

⚠ init-grid --force 주의

`init-grid --force` 는 `grid.properties` 기준으로 **완전히 새로운 그리드**를 생성한다. 손절 전 체결 이력은 모두 정리된다.

24시간 잠금을 강제 해제하려면 `reset-stop-loss --force` 를 먼저 실행한 후 `init-grid --force` 를 진행한다.

봇 재시작 후 손절 상태가 자동으로 복원되므로 별도의 손절 상태 초기화는 불필요하다.

### 손절 이벤트 로그

- **로그 파일:** `logs/trading-YYYY-MM-DD.log`
- **로그 레벨:** ERROR (CloudWatch, journalctl 연동)
- **형식:** `[STOP_LOSS] L{n} armed at ...` / `[STOP_LOSS] L{n} triggered`

log

```
2026-05-06 10:30:45,123 [main] ERROR [STOP_LOSS] L1 armed at 2026-05-06T10:30:45+00:00 (threshold=87300000)
2026-05-06 11:30:46,456 [main] ERROR [STOP_LOSS] L1 triggered: 50% liquidate (sold 0.0005 BTC)
```

### 외부 알림 (Slack / Webhook)

손절 이벤트를 Slack 또는 Generic Webhook으로 즉시 알림받을 수 있다.

properties

```
# Slack Incoming Webhook URL 또는 Generic Webhook URL
STOP_LOSS_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# 알림 활성화/비활성화 (기본값: True)
STOP_LOSS_NOTIFICATION_ENABLED=True
```

| 이벤트 | 색상 | 트리거 시점 | 포함 정보 |
| --- | --- | --- | --- |
| **ARMED** | 🟠 주황 | 손절 조건 충족 → 대기 시간 진입 | 현재가, 임계값, 하락률, 그리드 기준가 |
| **EXECUTED** | 🟢 초록 | 대기 시간 경과 → 청산 완료 | 현재가, 임계값, 청산수량 |
| **FAILED** | 🔴 빨강 | 청산 중 오류 발생 | 현재가, 임계값, 실패한 슬롯 정보 |

📌 알림 정책

- 알림 송신 실패가 발생해도 손절 본 흐름(포지션 청산)은 계속 진행
- Slack 형식은 attachments 페이로드로 전송
- 네트워크 단절이나 Webhook 서버 장애는 로그에 기록되지만 손절 흐름을 차단하지 않음

### 운영 중 설정 변경

1. EC2에서 `./stop.sh` 로 봇 정지
2. `grid.properties` 또는 `.env` 파일 수정
3. `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh` 로 재시작

✅ 재시작으로 반영되는 파라미터

`STOP_LOSS_MODE`, `STOP_LOSS_BAND_MULTIPLE`, 모든 `STOP_LOSS_*_CONSECUTIVE_CLOSES`, `STOP_LOSS_*_ARM_HOLD_SECONDS`, `STOP_LOSS_L1_LIQUIDATE_RATIO`

⚠ 그리드 생성 시에만 반영

`STOP_LOSS_CANDLE_UNIT` 은 이미 실행 중인 그리드는 이전 값으로 평가된다.

### 손절 비활성화

properties

```
STOP_LOSS_MODE=off
```

이 경우 봇은 현재가가 그리드 최하단 아래로 내려가도 아무 조치를 취하지 않는다. 모든 매수/매도는 정상 운영된다.
