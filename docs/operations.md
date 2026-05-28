# 운영 / 인프라 가이드

[auto](file:///C:/dev/mobileAuto/auto) 자동매매 봇의 EC2 운영, 배포, 점검, 손절 절차에 대한 가이드입니다.

---

## 📌 운영 정보 요약

### 🖥 EC2 서버 정보
- **IP 주소**: `43.202.113.123`
- **사용자**: `ubuntu`
- **SSH 키 경로**: `/home/yangyag/auto/aws/test-keypair.pem`
- **작업 디렉터리**: `/home/ubuntu/auto`

### ⚙ 봇 런타임
- **Python 실행 파일**: `.venv/bin/python`
- **진입점**: [main.py](file:///C:/dev/mobileAuto/auto/main.py)
- **환경 설정 파일**: [.env](file:///C:/dev/mobileAuto/auto/.env) (EC2 경로: `/home/ubuntu/auto/.env`)
- **로그 파일**: `logs/trading-YYYY-MM-DD.log`

### 🚀 핵심 제어 스크립트
- **시작**: [run.sh](file:///C:/dev/mobileAuto/auto/run.sh)
- **종료**: [stop.sh](file:///C:/dev/mobileAuto/auto/stop.sh)
- **로그 추적**: [tail-latest-log.sh](file:///C:/dev/mobileAuto/auto/tail-latest-log.sh)
- **일별 최저가 점검**: [check_daily_low.py](file:///C:/dev/mobileAuto/auto/scripts/check_daily_low.py)

### 🔁 Git & 브랜치
- **로컬 원격**: `git@github.com:yangyag/auto.git`
- **EC2 원격**: `https://github.com/yangyag/auto.git`
- **기본 브랜치**: `main`

---

## 문서 역할

- 이 문서는 이 저장소의 **인프라, 운영, 배포 기준**을 다룹니다.
- 프로그램 로직과 전략 설명은 [README.md](file:///C:/dev/mobileAuto/auto/README.md)를 참조하세요.
- 최초 가동 및 설치 절차는 [setup.md](file:///C:/dev/mobileAuto/auto/docs/setup.md)를 참조하세요.

---

## 로컬 / EC2 고정 정보 비교

| 항목 | 로컬 환경 | EC2 운영 환경 |
| :--- | :--- | :--- |
| **작업 디렉터리** | `/home/yangyag/auto` | `/home/ubuntu/auto` |
| **Git 원격 저장소** | `git@github.com:yangyag/auto.git` | `https://github.com/yangyag/auto.git` |
| **기본 브랜치** | `main` | `main` |
| **.env 경로** | `./.env` | `/home/ubuntu/auto/.env` |
| **가상환경 Python** | `.venv/bin/python` | `/home/ubuntu/auto/.venv/bin/python` |
| **봇 프로세스 패턴** | — | `.venv/bin/python /home/ubuntu/auto/main.py` |
| **SSH 접속 키** | `/home/yangyag/auto/aws/test-keypair.pem` | — |
| **SSH 접속 계정** | — | `ubuntu` |
| **서버 IP** | — | `43.202.113.123` |

> [!WARNING]
> **혼동 주의**: EC2 서버의 `/home/ubuntu/llm.env`는 다른 서비스용 설정 파일입니다. 자동매매 봇 저장소의 설정 파일([.env](file:///C:/dev/mobileAuto/auto/.env))로 착각하지 않도록 주의하세요.

---

## 운영 관련 파일

| 파일명 | 용도 |
| :--- | :--- |
| [setup.md](file:///C:/dev/mobileAuto/auto/docs/setup.md) | `git clone` 직후 설치, 초기 설정 및 실행 준비 가이드 |
| [README.md](file:///C:/dev/mobileAuto/auto/README.md) | 자동매매 프로그램 로직 및 구동 전략 설명 |
| [quick-commands.md](file:///C:/dev/mobileAuto/auto/docs/quick-commands.md) | 자주 쓰이는 운영 및 조회 명령 모음 (Cheat Sheet) |
| [.env_sample](file:///C:/dev/mobileAuto/auto/.env_sample) | 로컬 [.env](file:///C:/dev/mobileAuto/auto/.env) 작성을 위한 샘플 기준 파일 |
| [run.sh](file:///C:/dev/mobileAuto/auto/run.sh) | 봇 백그라운드 구동 스크립트 |
| [stop.sh](file:///C:/dev/mobileAuto/auto/stop.sh) | 가동 중인 백그라운드 봇 정상 종료 스크립트 |
| [tail-latest-log.sh](file:///C:/dev/mobileAuto/auto/tail-latest-log.sh) | 최신 날짜의 거래 로그 실시간 추적 스크립트 |
| `logs/trading-YYYY-MM-DD.log` | 매일 날짜별로 누적되는 트레이딩 운영 로그 |

---

## EC2 접속

로컬 터미널에서의 기본 SSH 접속 명령어:
```bash
chmod 600 /home/yangyag/auto/aws/test-keypair.pem
ssh -o StrictHostKeyChecking=no -i /home/yangyag/auto/aws/test-keypair.pem ubuntu@43.202.113.123
```

접속 후 프로젝트 루트 디렉터리로 이동:
```bash
cd /home/ubuntu/auto
```

---

## Git / 배포 기준

> [!NOTE]
> **커밋 메시지**: 별도의 요청이 없는 한 커밋 메시지는 **한국어** 작성을 원칙으로 합니다.

### EC2 배포 전 사전 상태 점검
```bash
git branch -vv
git status --short
test -f /home/ubuntu/auto/.env && echo env:present
ps -eo pid,args | grep '[p]ython /home/ubuntu/auto/main.py' \
  || ps -eo pid,args | grep '[p]ython3 /home/ubuntu/auto/main.py' \
  || ps -eo pid,args | grep '[p].venv/bin/python /home/ubuntu/auto/main.py'
```

### EC2 최신 커밋 배포 절차
1. `cd /home/ubuntu/auto` (작업 폴더 이동)
2. `./stop.sh` 로 백그라운드 봇 정지
3. `git fetch origin` (원격 브랜치 갱신)
4. `git status --short` 로 변경 사항 사전 점검
5. 필요 시 변경 사항 정리 후 `git pull --ff-only origin main` 실행
6. `.venv/bin/python -c "import main"` 으로 의존성 및 패키지 무결성 확인
7. `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh` 로 봇 재시작
8. `./tail-latest-log.sh` 혹은 최신 로그 뒷부분을 확인하여 정상 작동 검증

> [!CAUTION]
> **untracked 파일 보호**: EC2 서버에는 빌드/가상환경 폴더(`.venv/`), 각종 엑스포트 임시 파일 및 서브 스크립트 등 git 관리 외 파일들이 많습니다. **`git clean -fd`와 같은 파괴적 명령어는 사전 교차 검증 없이는 절대 실행하지 마십시오.**

---

## Python 실행 환경

### EC2 운영 환경
- EC2에는 `/home/ubuntu/auto/.venv` 가 이미 구성되어 있습니다. **가상환경을 새로 빌드하지 말고 기존 venv를 그대로 유지하여 사용합니다.**
- 터미널에서 직접 수동 조작할 때는 가상환경을 활성화합니다:
  ```bash
  source /home/ubuntu/auto/.venv/bin/activate
  ```
- 스크립트 내부나 원격 쉘 명령 등 activate 없이 바로 호출해야 하는 경우, 가상환경 내 파이썬의 절대 경로(`.venv/bin/python`)를 명시합니다.
- 패키지 의존성 파일([requirements.txt](file:///C:/dev/mobileAuto/auto/requirements.txt))이 변경된 경우에도 가상환경을 파괴하지 않고 추가 패키지만 증분 설치합니다:
  ```bash
  /home/ubuntu/auto/.venv/bin/python -m pip install -r requirements.txt
  ```

> [!WARNING]
> `.venv/` 폴더는 git untracked 파일이므로 `git clean` 등의 명령 실행 시 유실되지 않도록 특별히 보호되어야 합니다. 가상환경에 오류가 의심되면 재생성 전에 `python -c "import main"` 명령을 통해 근본 오류가 환경 문제인지 설정 문제인지 먼저 판별하십시오.

### 로컬 개발 환경
- 일부 환경에서는 시스템 `python3 -m venv .venv` 명령이 `ensurepip` 누락으로 실패할 수 있습니다.
- 동일한 오류 발생 시 `uv` 패키지 매니저를 통해 우회하여 가상환경을 빌드합니다:
  ```bash
  ~/.local/bin/uv venv --clear .venv
  ~/.local/bin/uv pip install --python .venv/bin/python pip
  ```
- 이후 검증 작업은 가상환경 내 파이썬을 호출해 진행합니다:
  ```bash
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -c "import main"
  .venv/bin/python -m unittest discover -s tests -v
  ```

---

## 운영 점검 기준

- **환경 설정 확인**: 봇 조작 전에 반드시 프로젝트 루트 또는 `/home/ubuntu/auto/.env`에 실제 구동용 설정 파일이 존재하는지 검증해야 합니다.
- **프로세스 확인**: 프로세스 가동 상태를 조회할 때는 단순히 `python3` 프로세스뿐만 아니라 `/home/ubuntu/auto/.venv/bin/python /home/ubuntu/auto/main.py` 패턴도 함께 검색하여 정합성을 맞춰야 합니다.
- **제어 표준**: 백그라운드 프로세스 제어는 임의의 `nohup`이나 백그라운드 커맨드가 아닌, 표준 관리 스크립트인 [run.sh](file:///C:/dev/mobileAuto/auto/run.sh) 및 [stop.sh](file:///C:/dev/mobileAuto/auto/stop.sh)를 사용해야 정상 종료 및 PID 추적이 원활합니다.
- **최저가 모니터링**: [check_daily_low.py](file:///C:/dev/mobileAuto/auto/scripts/check_daily_low.py) 스크립트를 주기적으로 구동하여 날짜별 실제 최저점 도달 여부와 그리드 매수 라인을 점검할 수 있습니다.
- **매도 잔량 검토**: [upbit_open_sell_monitor.py](file:///C:/dev/mobileAuto/auto/scripts/upbit_open_sell_monitor.py)를 구동하면 업비트의 가중평균 단가 착시를 우회하고, 개별 그리드 슬롯별 실제 취득 단가 대비 실시간 미실현 손익을 명확히 조회할 수 있습니다.

---

## 주문 관련 용어 정비

### 📌 `quantity` (발주 수량) vs `held_qty` (보유 수량)
- `orders` 테이블의 `quantity` 컬럼은 **최초에 시장에 요청한 주문량**입니다.
- 체결 지연이나 부분 체결 등으로 인해 실제 봇이 확보한 수량은 다를 수 있으므로, 정확한 재고 매칭을 계산할 때는 반드시 `GridState.held_qty` 값을 기준으로 판단해야 합니다.

---

## 라이브 예산 조정 주의사항

### 💰 [adjust_budget_live.py](file:///C:/dev/mobileAuto/auto/scripts/adjust_budget_live.py) 사용
- 가동 중인 봇의 총예산을 조정할 때 사용되는 스크립트입니다.
- 본 도구는 **절대 예산값**(`--target-budget`)을 인수로 받아 구동되며, 기존 그리드의 가격 구간과 이미 체결된 보유 수량은 건드리지 않고 **앞으로 매수할 대기 수량 및 계획 금액만 재계산**하여 DB를 업데이트합니다.

---

## 자격증명 / 민감정보 보호 원칙

- 업비트 API Key 등 민감 인증정보는 오직 환경변수 `UPBIT_ACCESS_KEY` 및 `UPBIT_SECRET_KEY`를 통해서만 주입되도록 설계되어 있습니다.
- DB 연결 계정 정보 또한 루트 [.env](file:///C:/dev/mobileAuto/auto/.env)를 통해서만 관리되어야 합니다.
- 어떠한 상황에서도 소스 코드, 주석, 혹은 공개 문서 내에 실제 비밀번호나 API 키가 기록되어 커밋되지 않도록 통제해야 합니다.

---

## 손절(Stop-Loss) 운영 가이드

손절 모듈은 현재 시세가 설정된 그리드의 최하단 가격 아래로 급락할 때, 단계적 가드를 발동하고 필요 시 포지션을 정리하여 추가 자산 유실을 방지합니다. 이론 및 세부 알고리즘 설계는 [strategy-formulas.md](file:///C:/dev/mobileAuto/auto/docs/strategy-formulas.md)의 관련 섹션을 참조하세요.

### 1. 손절 모드 설정

손절 매커니즘은 [grid.properties](file:///C:/dev/mobileAuto/auto/grid.properties) 또는 환경 변수를 통해 관리됩니다. (기본 권장값: `band_multiple` 모드)

```properties
# 활성화 모드: band_multiple (그리드 간격 비례 권장) | fixed_pct (고정 %) | off (비활성)
STOP_LOSS_MODE=band_multiple

# band_multiple 모드 전용: 그리드 폭의 배수 기반 마진 (k값, 권장 범위 1.0 ~ 2.0)
STOP_LOSS_BAND_MULTIPLE=1.5

# fixed_pct 모드 전용 (백테스트 및 단순 퍼센트 비교용)
STOP_LOSS_L0_PCT=10
STOP_LOSS_L1_PCT=20
STOP_LOSS_L2_PCT=30
```

---

### 2. 손절 레벨별 봇 제어 로직

#### 🟢 LEVEL 0 (경계)
- **트리거**: 현재가 < L0 손절 임계값 (예: 그리드 하단 대비 약 -10% 영역 돌파)
- **봇 거동**: **신규 매수 주문만 즉시 차단**됩니다. 기존에 걸려있는 이익 실현(TP) 매도 주문은 그대로 정상 유지됩니다.
- **재개 조건**: 현재가가 다시 L0 임계값 위로 올라가면 **자동으로 정상 모드로 복구**됩니다. (가역적 복구 지원)

#### 🟡 LEVEL 1 (부분 청산)
- **트리거**: 현재가 < L1 손절 임계값 (예: 그리드 하단 대비 약 -20% 영역 돌파)
- **봇 거동**: 트리거 확정 시 **신규 매수를 영구 차단**하며, 대기 시간(기본 1시간) 동안 추세를 관측한 뒤 보유 BTC의 **50%를 지정가로 매도** 처리합니다.
- **재개 조건**: CLI를 통해 수동으로 `reset-stop-loss` 명령을 입력하여 잠금 상태를 복구해야 매수가 재개됩니다.

#### 🔴 LEVEL 2 (전량 청산)
- **트리거**: 현재가 < L2 손절 임계값 (예: 그리드 하단 대비 약 -30% 영역 돌파)
- **봇 거동**: 트리거 즉시 **모든 매수 차단 및 30분 대기 후 잔여 보유 수량 100%를 시장가로 분할 매도(청산)**합니다. 청산 완료 후 봇 프로세스는 강제 종료되며, 24시간 동안 재시작이 차단됩니다.
- **재개 조건**: DB 내 강제 잠금이 해제되어야 하며, 일반적으로 `init-grid --force` 명령을 통해 완전히 새로운 가격대 그리드를 재수립해야 재가동할 수 있습니다.

---

### 3. 손절 환경 변수 파라미터 정보

| 파라미터 명 | 기본값 | 용도 | 권장 범위 | 상세 설명 |
| :--- | :---: | :--- | :---: | :--- |
| `STOP_LOSS_MODE` | `band_multiple` | 손절 알고리즘 모드 | `band_multiple`, `fixed_pct`, `off` | `band_multiple` 모드 가동을 강력히 권장 |
| `STOP_LOSS_BAND_MULTIPLE` | `1.5` | 그리드 하단 폭 배수 | `1.0 ~ 2.0` | 임계값 = $MinBuyPrice \times (1 - k \times band\_ratio)$ |
| `STOP_LOSS_L0_PCT` | `10` | L0 고정 하락폭 (%) | `5 ~ 15` | `fixed_pct` 모드 가동 시 적용 |
| `STOP_LOSS_L1_PCT` | `20` | L1 고정 하락폭 (%) | `15 ~ 25` | `fixed_pct` 모드 가동 시 적용 |
| `STOP_LOSS_L2_PCT` | `30` | L2 고정 하락폭 (%) | `25 ~ 35` | `fixed_pct` 모드 가동 시 적용 |
| `STOP_LOSS_CANDLE_UNIT` | `15` | 추세 판정 캔들 주기 (분) | `5 ~ 60` | 손절 조건 판단 시 참조할 캔들 종가 데이터의 기준 분 |
| `STOP_LOSS_L0_CONSECUTIVE_CLOSES` | `4` | L0 캔들 연속 확정 수 | `2 ~ 6` | 지정 횟수 연속으로 종가가 임계값 하회 시 트리거 |
| `STOP_LOSS_L1_CONSECUTIVE_CLOSES` | `4` | L1 캔들 연속 확정 수 | `2 ~ 6` | L1 손절 확정을 위한 연속 종가 하회 기준 |
| `STOP_LOSS_L2_CONSECUTIVE_CLOSES` | `2` | L2 캔들 연속 확정 수 | `1 ~ 4` | L2는 빠른 가드가 필요하므로 연속 횟수를 낮춰 판정 |
| `STOP_LOSS_L1_ARM_HOLD_SECONDS` | `3600` | L1 확정 후 대기 시간 (초) | `600 ~ 3600` | 트리거 확정 후 실제 분할 매도 주문 제출 전 대기 시간 (1시간) |
| `STOP_LOSS_L2_ARM_HOLD_SECONDS` | `1800` | L2 확정 후 대기 시간 (초) | `300 ~ 1800` | 트리거 확정 후 전량 시장가 매도 실행 전 대기 시간 (30분) |
| `STOP_LOSS_L1_LIQUIDATE_RATIO` | `0.5` | L1 보유량 청산 비율 | `0.3 ~ 0.7` | L1 발동 시 매도할 비율 (0.5 = 50%) |
| `STOP_LOSS_RESTART_LOCKOUT_HOURS` | `24` | L2 이후 재시작 금지 시간 | `12 ~ 48` | L2 완전 청산 후 시스템 강제 쿨다운 주기 |
| `STOP_LOSS_WEBHOOK_URL` | (없음) | 알림 Webhook 주소 | URL 문자열 | Slack Incoming Webhook 등 외부 메신저 URL |
| `STOP_LOSS_NOTIFICATION_ENABLED` | `True` | 외부 메신저 알림 여부 | `True`, `False` | 알림 전송 기능 켜기/끄기 |

---

### 4. 수동 손절 해제 방법 (`reset-stop-loss` CLI)

L1이 가동되어 매수가 중단된 상태를 수동으로 해제하거나, L2 청산 후 24시간 재부팅 잠금 필터를 우회해야 할 때 사용합니다.

```bash
# 1. EC2 접속 및 작업 디렉터리 이동
cd /home/ubuntu/auto
source .venv/bin/activate

# 2. L1 매수 잠금 상태 기본 해제
python main.py reset-stop-loss

# 3. L2 재부팅 잠금 강제 해제 (24시간 쿨다운 필터 우회 - 긴급용)
python main.py reset-stop-loss --force
```

> [!IMPORTANT]
> - `reset-stop-loss` 명령은 기존에 열려 있는 이익 실현(TP) 매도 상태는 건드리지 않고, 차단된 매수 기능만 정상 가동 상태(`stop_loss_active = false`)로 안전하게 되돌립니다.
> - L2 청산이 완료된 상태는 잔고가 모두 시장가로 매도되어 비어 있으므로, 강제 해제 후 반드시 `init-grid --force` 명령을 통해 새로운 단가의 그리드 계단을 놓아주어야 봇이 재가동됩니다.

---

### 5. L2 손절 후 시스템 재구축 가이드

L2 손절이 완전히 확정되어 청산 작업이 끝나면 다음과 같이 조치합니다.

1. 백그라운드 봇이 자동으로 구동 루프를 빠져나와 안전하게 중단됩니다.
2. 모든 포지션은 매도가 완료된 상태입니다.
3. DB 테이블 내에 손절 청산 타임스탬프(`liquidated_at`) 및 잠금 플래그들이 영속 저장됩니다.
4. 신규 가격 그리드로 봇을 재구동하기 위해 아래 명령어를 수행합니다.

```bash
# EC2 환경
cd /home/ubuntu/auto
./stop.sh

# 1. 필요시 최신 안정 코드로 갱신
git fetch origin && git pull --ff-only origin main

# 2. 새로운 가격 구간으로 그리드 재생성 (기존 손절 기록이 초기화되며 새로 운용을 시작합니다)
.venv/bin/python main.py init-grid --force

# 3. 봇 재구동 및 로그 점검
PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh
./tail-latest-log.sh
```

---

### 6. 손절 외부 알림 구성 (Slack/Webhook)

손절 작동 상태(ARMED / EXECUTED / FAILED)를 실시간으로 Slack 채널 등에 받아볼 수 있습니다.

**[grid.properties](file:///C:/dev/mobileAuto/auto/grid.properties) 설정**:
```properties
STOP_LOSS_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
STOP_LOSS_NOTIFICATION_ENABLED=True
```

#### 🔔 알림 레벨 속성

| 상태 유형 | 색상 코드 | 발송 타이밍 | 알림 포함 정보 |
| :--- | :---: | :--- | :--- |
| **ARMED** (대입) | 🟠 주황 | 손절 캔들 기준 충족 시 (대기 진입) | 현재 가격, 임계값, 하락률, 기준 그리드 정보 |
| **EXECUTED** (수행) | 🟢 초록 | 대기 시간 종료 후 실제 청산 완료 시 | 체결 가격, 실제 청산 수량, 완료 시각 |
| **FAILED** (실패) | 🔴 빨강 | 주문 제출이나 네트워크 장애 등 오류 발생 시 | 에러 내용, 오류 발생 슬롯 명세 |

> [!NOTE]
> 알림 발송 중의 일시적 통신 지연이나 Webhook API 서버 장애는 로그에만 경고를 남기며, 봇 내부의 핵심 손절 청산 메커니즘 구동을 방해하거나 멈추게 하지 않습니다.
