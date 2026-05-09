# 운영 / 인프라 가이드

## 문서 역할
- 이 문서는 이 저장소의 인프라, 운영, 배포 기준만 다룬다.
- 프로그램 로직과 전략 설명은 `README.md`를 본다.
- 처음 설치 절차는 `setup.md`를 본다.

## 로컬 / EC2 고정 정보
- 로컬 작업 디렉터리: `/home/yangyag/auto`
- 로컬 Git 원격: `origin = git@github.com:yangyag/auto.git`
- 로컬 기본 브랜치: `main`
- EC2 운영 서버: `43.202.113.123`
- EC2 SSH 사용자: `ubuntu`
- EC2 접속에 실제로 써온 로컬 키 경로: `/home/yangyag/auto/aws/test-keypair.pem`
- EC2 자동매매 저장소 경로: `/home/ubuntu/auto`
- EC2 자동매매 `.env` 경로: `/home/ubuntu/auto/.env`
- EC2 자동매매 가상환경 Python: `/home/ubuntu/auto/.venv/bin/python`
- EC2 봇 프로세스 패턴: `/home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py`
- EC2 Git 원격: `origin = https://github.com/yangyag/auto.git`
- EC2 기본 브랜치: `main`
- 같은 서버의 `/home/ubuntu/llm.env` 는 다른 서비스용 파일이다. 자동매매 저장소 설정 파일로 착각하면 안 된다.

## 운영 관련 파일
- `setup.md`: git clone 직후 설치, 초기 설정, 첫 실행 준비
- `README.md`: 프로그램 로직과 전략 설명
- `docs/quick-commands.md`: 자주 쓰는 운영 명령 모음
- `.env_sample`: 로컬 `.env` 작성 기준
- `run.sh`: 백그라운드 실행
- `stop.sh`: 백그라운드 종료
- `tail-latest-log.sh`: 최신 날짜 로그 추적
- `logs/trading-YYYY-MM-DD.log`: 운영 로그

## EC2 접속
기본 SSH 예시:

```bash
chmod 600 /home/yangyag/auto/aws/test-keypair.pem
ssh -o StrictHostKeyChecking=no -i /home/yangyag/auto/aws/test-keypair.pem ubuntu@43.202.113.123
```

EC2에 붙은 뒤 기본 위치:

```bash
cd /home/ubuntu/auto
```

## Git / 배포 기준
- Git 커밋 메시지는 사용자가 다른 언어를 명시하지 않는 한 한국어를 우선한다.

EC2에서 먼저 확인할 것:
- `git branch -vv`
- `git status --short`
- `test -f /home/ubuntu/auto/.env && echo env:present`
- `ps -eo pid,args | grep '[p]ython /home/ubuntu/auto/main.py' || ps -eo pid,args | grep '[p]ython3 /home/ubuntu/auto/main.py' || ps -eo pid,args | grep '[p]ython /home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py' || ps -eo pid,args | grep '[p].venv/bin/python /home/ubuntu/auto/main.py'`

EC2에 최신 커밋 반영 기본 순서:
1. `cd /home/ubuntu/auto`
2. `./stop.sh`
3. `git fetch origin`
4. `git status --short`로 tracked 변경 확인
5. 필요 시 변경 정리 후 `git pull --ff-only origin main`
6. `.venv`가 깨지지 않았는지 `/home/ubuntu/auto/.venv/bin/python -c "import main"` 확인
7. `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh`
8. `./tail-latest-log.sh` 또는 `tail -n 50 logs/trading-$(date +%F).log`

주의:
- EC2에서 `.venv/`, export 결과 파일, 보조 스크립트 같은 untracked 파일이 남아 있을 수 있으므로 `git clean -fd` 같은 파괴적 정리는 먼저 확인 없이 하지 않는다.
- pull 이 tracked 변경과 충돌하면 무작정 되돌리지 말고 어떤 파일인지 먼저 확인한다.

## Python 실행 환경 메모

### EC2
- EC2에는 `/home/ubuntu/auto/.venv` 가 이미 구성되어 있다. 새로 만들지 말고 기존 venv 를 그대로 사용한다.
- 쉘에서 직접 작업할 때는 activate 스크립트로 활성화한다.

```bash
source /home/ubuntu/auto/.venv/bin/activate
```

- 배포 스크립트나 원격 명령처럼 activate 없이 실행할 때는 `.venv/bin/python` 절대 경로를 직접 호출한다. `run.sh` 도 `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh` 형태로 넘긴다.
- `requirements.txt` 가 변경되어 의존성을 재설치해야 할 때도 `.venv` 를 재생성하지 말고 기존 venv 에 설치만 추가한다.

```bash
/home/ubuntu/auto/.venv/bin/python -m pip install -r requirements.txt
```

- `.venv/` 는 git untracked 상태가 정상이다. `git clean -fd` 같은 파괴적 정리 대상에서 반드시 제외한다.
- venv 가 실제로 깨졌다고 판단되면 재생성 전에 먼저 `/home/ubuntu/auto/.venv/bin/python -c "import main"` 로 실패 원인을 확인한다. import 가 되면 venv 자체 문제가 아니라 설정/의존성 문제일 가능성이 높다.

### 로컬
- 이 작업 디렉터리는 시스템 `python3 -m venv .venv` 가 `ensurepip` 부재로 실패할 수 있다.
- 같은 문제가 다시 나오면 우선 `uv`로 가상환경을 만든다.

```bash
~/.local/bin/uv venv --clear .venv
~/.local/bin/uv pip install --python .venv/bin/python pip
```

- 이후 의존성 설치와 검증은 가능하면 `.venv/bin/python` 기준으로 실행한다.

```bash
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
- 테스트 로그가 같은 날짜 파일에 남을 수 있으므로 로거 이름 `__main__` / `main`도 함께 확인한다.
- 실거래 주문이 발생할 수 있는 루프 실행은 명시적으로 필요할 때만 한다.

## 주문 관련 용어
- `orders` 테이블의 `quantity` 컬럼은 최초 발주량이다. 부분 체결 시 실제 체결량과 다를 수 있으므로 실 체결량은 `GridState.held_qty`를 참조한다. 사고 분석 시 두 값을 함께 본다.

## 라이브 예산 조정 주의
- `scripts/adjust_budget_live.py`는 절대 총예산(`--target-budget`)으로 운영되며, 현재 그리드의 가격 구조와 보유 수량을 유지한 채 계획 수량만 재계산한다.

## 자격증명 / 민감정보 원칙
- API 키는 환경변수 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`로만 주입한다.
- PostgreSQL 접속정보도 프로젝트 루트 `.env` 또는 EC2 `/home/ubuntu/auto/.env`로만 관리한다.
- 민감정보를 문서, 샘플 파일, 커밋에 복제하지 않는다.

## 손절(Stop-Loss) 운영 가이드

### 개요

손절 기능은 현재가가 그리드 최하단 아래로 내려갔을 때 단계별 자동 대응을 제공한다. 설정된 임계값에 도달하고 컨펌 조건이 만족되면 자동으로 포지션을 청산한다.

자세한 설계와 이론은 [docs/stop-loss-design.md](stop-loss-design.md)를 참조한다.

### 손절 모드 활성화

손절 기능은 `grid.properties` 또는 환경변수로 제어된다. 기본값은 `band_multiple` 모드로 활성화되어 있다:

```properties
# 모드: band_multiple (권장) | fixed_pct | off
STOP_LOSS_MODE=band_multiple

# band_multiple 모드: 그리드 폭 배수 기반 임계값 (권장)
STOP_LOSS_BAND_MULTIPLE=1.5        # k값, 범위 1.0~2.0

# fixed_pct 모드: 고정 퍼센트 기반 (백테스트/비교용)
STOP_LOSS_L0_PCT=10
STOP_LOSS_L1_PCT=20
STOP_LOSS_L2_PCT=30
```

### ENV 파라미터 표

| 파라미터 | 기본값 | 의미 | 권장 범위 | 설명 |
|---------|--------|------|----------|------|
| `STOP_LOSS_MODE` | `band_multiple` | 손절 모드 | `band_multiple` / `fixed_pct` / `off` | band_multiple 권장 (그리드 폭이 달라져도 일관된 기준) |
| `STOP_LOSS_BAND_MULTIPLE` | `1.5` | 그리드 폭 배수 | 1.0 ~ 2.0 | 임계값 = min × (1 - k × band_ratio) |
| `STOP_LOSS_L0_PCT` | `10` | L0 고정 % | 5 ~ 15 | band_multiple 모드에서는 사용 안 됨 |
| `STOP_LOSS_L1_PCT` | `20` | L1 고정 % | 15 ~ 25 | band_multiple 모드에서는 사용 안 됨 |
| `STOP_LOSS_L2_PCT` | `30` | L2 고정 % | 25 ~ 35 | band_multiple 모드에서는 사용 안 됨 |
| `STOP_LOSS_CANDLE_UNIT` | `15` | 캔들 단위 (분) | 5 ~ 60 | 손절 트리거 컨펌용 캔들 종가 분석 |
| `STOP_LOSS_L0_CONSECUTIVE_CLOSES` | `4` | L0 연속 캔들 | 2 ~ 6 | 이 개수의 캔들이 연속으로 L0 임계 아래 종가해야 트리거 |
| `STOP_LOSS_L1_CONSECUTIVE_CLOSES` | `4` | L1 연속 캔들 | 2 ~ 6 | |
| `STOP_LOSS_L2_CONSECUTIVE_CLOSES` | `2` | L2 연속 캔들 | 1 ~ 4 | L2는 위험하므로 더 빠르게 컨펌 |
| `STOP_LOSS_L1_ARM_HOLD_SECONDS` | `3600` | L1 대기 시간 (초) | 600 ~ 3600 | 컨펌 후 손절 실행까지의 추가 대기 시간 (1시간) |
| `STOP_LOSS_L2_ARM_HOLD_SECONDS` | `1800` | L2 대기 시간 (초) | 300 ~ 1800 | 컨펌 후 손절 실행까지의 추가 대기 시간 (30분) |
| `STOP_LOSS_L1_LIQUIDATE_RATIO` | `0.5` | L1 청산 비율 | 0.3 ~ 0.7 | L1에서 청산할 포지션 비율 (0=0%, 1=100%) |
| `STOP_LOSS_RESTART_LOCKOUT_HOURS` | `24` | L2 재시작 잠금 | 12 ~ 48 | L2 발동 후 자동 재시작 금지 시간 |
| `STOP_LOSS_WEBHOOK_URL` | (없음) | 외부 알림 Webhook | URL 문자열 | Slack/Generic Webhook URL. 비어있으면 알림 미발송 |
| `STOP_LOSS_NOTIFICATION_ENABLED` | `True` | 외부 알림 활성화 | `True` / `False` | False로 설정하면 WEBHOOK_URL이 있어도 알림 미발송 |

### L0/L1/L2 트리거 시 봇 거동

| 단계 | 트리거 조건 | 봇 거동 | 재개 방법 |
|-----|-----------|--------|---------|
| **L0** | 현재가 < L0 임계값 (기본 -10%) | 신규 매수만 차단. 손절 본 흐름은 실행하지 않음. 기존 TP 매도는 정상 진행. 가역적. | 현재가가 L0 임계값 위로 회복하면 자동 해제 |
| **L1** | 현재가 < L1 임계값 (기본 -20%) | 컨펌 후 1시간 대기하여 보유 BTC 50%를 threshold 가격 지정가로 매도. 매수 영구 차단. | `reset-stop-loss` CLI로 수동 해제. STOP_LOSS_RESTART_LOCKOUT_HOURS 미경과 시 exit 2 반환. |
| **L2** | 현재가 < L2 임계값 (기본 -30%) | 컨펌 후 30분 대기하여 잔여 100%를 시장가로 분할 청산. 봇 즉시 종료 (프로세스 exit). 24시간 재시작 잠금. | 새 그리드로 `init-grid --force` 재구성 |

### reset-stop-loss CLI 사용법

L1 발동 후 매수 차단을 해제하거나 L2 24시간 잠금을 강제 해제하려면 `reset-stop-loss` 명령을 사용한다:

```bash
# EC2에서 (venv 활성화 또는 절대 경로 사용)
cd /home/ubuntu/auto
source .venv/bin/activate

# L1 해제
python main.py reset-stop-loss

# L2 24시간 잠금 강제 해제 (--force 옵션)
python main.py reset-stop-loss --force

# 또는 절대 경로:
/home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py reset-stop-loss [--force]
```

**역할:**
- **기본 (L1 해제):** 
  - 기존 포지션의 상태 보존 (L1 청산 이후 남은 TP 매도 주문은 그대로 유지)
  - L1 매수 영구 차단 해제 (새 매수 신호에서 다시 매수 가능)
  - `stop_loss_active` 상태를 false로 복구
  
- **--force 옵션 (L2 강제 해제):**
  - STOP_LOSS_RESTART_LOCKOUT_HOURS 미경과 상태에서도 24시간 잠금을 강제 해제
  - L2 발동 후 모든 포지션이 청산되었으므로, 새 그리드 없이 매수 재개 가능
  - 긴급 상황에서 24시간 대기 없이 즉시 봇 재시작 필요시 사용

- **운영 로그:** `[STOP_LOSS] reset-stop-loss completed` 기록

**주의:** 
- --force 없이 STOP_LOSS_RESTART_LOCKOUT_HOURS 미경과 상태에서 호출하면 exit 2로 실패
- L2 이후는 포지션이 모두 청산되었으므로 `init-grid --force`로 새 그리드를 생성해야 봇 재시작 가능
- --force는 L2 강제 해제용이므로, L1 상태에서는 --force 없이 호출하는 것을 권장

### L2 후 재시작 절차

L2 손절이 발동되면:
1. 봇이 자동으로 종료된다 (프로세스 exit, 메인 루프 탈출)
2. 모든 포지션이 청산된다 (시장가 분할 매도)
3. `liquidated_at` 타임스탐프가 DB에 기록된다
4. 24시간 동안 자동 재시작이 차단된다
5. 손절 상태 (`stop_loss_armed_at`, `stop_loss_active` 등)는 DB에 영속화되어 봇 재시작 후 복원됨

**재시작 방법:**
```bash
cd /home/ubuntu/auto
./stop.sh
git fetch origin && git pull --ff-only origin main  # 필요시 코드 동기화
.venv/bin/python main.py init-grid --force         # 새 그리드 생성 (기존 상태 초기화)
PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh
./tail-latest-log.sh
```

**주의:**
- `init-grid --force`는 `grid.properties` 기준으로 **완전히 새로운 그리드**를 생성한다. 따라서 손절 전 체결 이력은 모두 정리된다.
- 24시간 잠금을 강제 해제하려면 `reset-stop-loss --force`를 먼저 실행한 후 `init-grid --force`를 진행한다.
- 봇 재시작 후 손절 상태가 자동으로 복원되므로 별도의 손절 상태 초기화는 불필요하다.

### 손절 이벤트 로그

손절 관련 이벤트는 다음과 같이 기록된다:

- **로그 파일**: `logs/trading-YYYY-MM-DD.log`
- **로그 레벨**: ERROR (CloudWatch, journalctl 연동)
- **형식**: `[STOP_LOSS] L{n} armed at {armed_at}` / `[STOP_LOSS] L{n} triggered`

```
2026-05-06 10:30:45,123 [main] ERROR [STOP_LOSS] L1 armed at 2026-05-06T10:30:45+00:00 (threshold=87300000)
2026-05-06 11:30:46,456 [main] ERROR [STOP_LOSS] L1 triggered: 50% liquidate (sold 0.0005 BTC)
```

### 외부 알림 (Slack/Webhook)

손절 이벤트를 Slack 또는 Generic Webhook으로 즉시 알림받을 수 있다.

**활성화:**
```properties
# Slack Incoming Webhook URL 또는 Generic Webhook URL
STOP_LOSS_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# 알림 활성화/비활성화 (기본값: True)
STOP_LOSS_NOTIFICATION_ENABLED=True
```

**알림 종류 및 페이로드:**

| 이벤트 | 색상 | 트리거 시점 | 포함 정보 |
|--------|------|-----------|---------|
| **ARMED** | 주황 | 손절 조건 충족 → 대기 시간 진입 | 현재가, 임계값, 하락률, 그리드 기준가 |
| **EXECUTED** | 초록 | 대기 시간 경과 → 포지션 청산 완료 | 현재가, 임계값, 청산수량 |
| **FAILED** | 빨강 | 청산 중 오류 발생 | 현재가, 임계값, 실패한 슬롯 정보 |

**설정 상세:**
- `STOP_LOSS_WEBHOOK_URL`: Slack Incoming Webhook URL 또는 Generic Webhook URL
  - 비어있으면 알림 송신이 자동 skip됨
  - 유효한 URL만 설정하면 알림 송신 시작
- `STOP_LOSS_NOTIFICATION_ENABLED`: 알림 활성화/비활성화 (기본 True)
  - False로 설정하면 `WEBHOOK_URL`이 있어도 알림 미발송

**주의:**
- 알림 송신 실패가 발생해도 손절 본 흐름(포지션 청산)은 계속 진행된다
- Slack 형식은 attachments 페이로드로 전송됨
- 네트워크 단절이나 Webhook 서버 장애는 로그에 기록되지만 손절 흐름을 차단하지 않음

### 운영 중 설정 변경

손절 파라미터를 변경하려면:

1. EC2에서 `./stop.sh`로 봇 정지
2. `grid.properties` 또는 `.env` 파일 수정
3. `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh`로 재시작

**변경 대상이 되는 파라미터** (재시작으로 반영):
- `STOP_LOSS_MODE`, `STOP_LOSS_BAND_MULTIPLE`
- 모든 `STOP_LOSS_*_CONSECUTIVE_CLOSES`, `STOP_LOSS_*_ARM_HOLD_SECONDS`
- `STOP_LOSS_L1_LIQUIDATE_RATIO`

**변경 대상이 아닌 파라미터** (그리드 생성 시에만 반영):
- `STOP_LOSS_CANDLE_UNIT` (이미 실행 중인 그리드는 이전 값으로 평가)

### 손절 비활성화

손절을 완전히 비활성화하려면:

```properties
STOP_LOSS_MODE=off
```

이 경우 봇은 현재가가 그리드 최하단 아래로 내려가도 아무 조치를 취하지 않는다. 모든 매수/매도는 정상 운영된다.
