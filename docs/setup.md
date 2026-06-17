# 설치 / 초기 설정 가이드

[auto](..) 자동매매 봇을 `git clone`한 직후 PostgreSQL 기반으로 초기 실행 가능한 상태까지 만드는 12단계 절차입니다.

---

## 📌 런타임 & 환경 요약

| 항목 | Python 가상환경 (`.venv`) | 환경 설정 (`.env`) | 데이터베이스 (PostgreSQL) | 그리드 설정 & 제어 |
| :--- | :--- | :--- | :--- | :--- |
| **기본 경로** | `.venv/` | [.env](../.env) | `postgres:18` | [grid.properties](../grid.properties) |
| **생성/설정** | `python3 -m venv .venv` | cp [.env_sample](../.env_sample) [.env](../.env) | 스키마: `auto_trading` (또는 `PGSCHEMA`) | [apply_grid_properties_to_postgres.py](../scripts/apply_grid_properties_to_postgres.py) |
| **대체/참조** | `uv venv --clear .venv` | [settings.py](../app/config/settings.py) | 마이그: [db/migrations/](../db/migrations) | [run.sh](../run.sh) / [stop.sh](../stop.sh) |
| **실행/주입** | `.venv/bin/python` | EC2: `/home/ubuntu/auto/.env` | 키: `STATE_BOT_KEY` | [tail-latest-log.sh](../tail-latest-log.sh) |

---

## 문서 개요

이 문서는 이 저장소를 **git clone 한 직후** 처음 설치하고, PostgreSQL 기반으로 초기 실행 가능한 상태까지 만드는 절차를 정리한 가이드입니다.

### 문서 역할 분담
- **프로그램 로직 및 전략 설명**: [README.md](../README.md)
- **EC2, git, 배포, 운영 인프라**: [operations.md](../docs/operations.md)

### 기준 운영 방식

| 항목 | 값 |
| :--- | :--- |
| **거래소** | 업비트 단일 마켓 (`cfg.SYMBOL` 설정값, 예: `KRW-BTC` / `KRW-USDT`) |
| **상태 저장** | PostgreSQL |
| **그리드 입력** | [grid.properties](../grid.properties) |
| **그리드 반영** | [apply_grid_properties_to_postgres.py](../scripts/apply_grid_properties_to_postgres.py) |
| **봇 실행/종료** | [run.sh](../run.sh) / [stop.sh](../stop.sh) |

> [!IMPORTANT]
> 아래 12개 단계는 **순서대로** 진행해야 합니다. 각 단계별 필수/선택 여부를 확인하세요.

---

## 1단계. 준비물

### 필수 항목
- **Git**
- **Python 3.11+**
- **PostgreSQL 접속 정보** (호스트, 포트, DB명, 사용자, 비밀번호)
- **업비트 API 키** (Access Key, Secret Key)
- **네트워크**: 업비트 REST/WebSocket 엔드포인트로 나가는 outbound 연결 허용

### 선택 항목
- `uv` (가상환경 생성이 안 될 때 대비)
- **Docker** (`postgres:18`을 로컬에 신속하게 띄우고 싶을 때)

> [!WARNING]
> **API 키 사전 발급**: 업비트 API 키는 미리 발급해 두어야 하며, 절대 코드, 문서, Git 커밋 등에 노출하거나 복사해 넣어서는 안 됩니다.

---

## 2단계. 저장소 받기 `[필수]`

SSH 키가 등록되어 있는 경우:
```bash
git clone git@github.com:yangyag/auto.git
cd auto
```

HTTPS를 사용하는 경우:
```bash
git clone https://github.com/yangyag/auto.git
cd auto
```

---

## 3단계. 가상환경 생성 `[필수]`

기본 Python venv 생성:
```bash
python3 -m venv .venv
```

만약 `ensurepip` 오류 등으로 생성이 실패할 경우, `uv`를 사용해 생성할 수 있습니다:
```bash
~/.local/bin/uv venv --clear .venv
~/.local/bin/uv pip install --python .venv/bin/python pip
```

> [!TIP]
> 우분투 등의 환경에서 시스템 venv 생성이 안 될 때는 `uv`를 사용하면 별도의 설정 없이 가상환경을 깨끗하게 구축할 수 있습니다.

---

## 4단계. 의존성 설치 `[필수]`

생성된 가상환경에 필요한 패키지들을 설치합니다.
```bash
.venv/bin/python -m pip install -r requirements.txt
```

---

## 5단계. `.env` 작성 `[필수]`

샘플 설정 파일을 복사하여 실제 환경 설정 값을 반영한 [.env](../.env) 파일을 생성합니다.
```bash
cp .env_sample .env
```

**최소 환경 변수 설정 예시**:
```env
UPBIT_ACCESS_KEY=YOUR_UPBIT_ACCESS_KEY
UPBIT_SECRET_KEY=YOUR_UPBIT_SECRET_KEY

# WebSocket 설정
UPBIT_WS_PUBLIC_ENABLED=true
UPBIT_WS_EVENT_LOOP_ENABLED=true
UPBIT_WS_EVENT_MIN_INTERVAL_SECONDS=3

# 거래 대상 마켓 (cfg.SYMBOL) — 봇이 매매할 단일 마켓을 결정
SYMBOL=KRW-USDT

# 상태 저장 백엔드
STATE_BACKEND=postgres

# 봇 식별 고유 키
STATE_BOT_KEY=krw-btc-live

# PostgreSQL 연결 정보
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=yangyag
PGUSER=yangyag
PGPASSWORD=YOUR_DB_PASSWORD
PGSCHEMA=auto_trading
```

> [!WARNING]
> - [settings.py](../app/config/settings.py)는 프로젝트 루트의 [.env](../.env)를 기준으로 설정을 읽습니다.
> - 실시간 가격은 Public Ticker WebSocket 이벤트를 기본으로 사용하며, WebSocket 장애나 이벤트가 들어오지 않을 경우 5초 주기 REST 폴링 방식으로 자동 Fallback 됩니다.
> - EC2 운영 서버 기준 자동매매 봇의 `.env` 경로는 `/home/ubuntu/auto/.env` 입니다.

---

## 6단계. PostgreSQL 준비 `[선택]`

이미 사용할 수 있는 PostgreSQL 서버가 있다면 이 단계를 건너뛰고 [.env](../.env) 파일의 연결 정보만 수정하면 됩니다.

만약 로컬 환경에서 Docker를 사용하여 빠르게 DB를 구성하고 싶다면 아래 명령어를 실행합니다.
```bash
docker run -d \
  --name auto-postgres \
  -e POSTGRES_DB=yangyag \
  -e POSTGRES_USER=yangyag \
  -e POSTGRES_PASSWORD=YOUR_DB_PASSWORD \
  -p 5432:5432 \
  -v auto_postgres_data:/var/lib/postgresql/data \
  postgres:18
```

> [!TIP]
> 저장소 루트에는 [docker-compose.yml](../docker-compose.yml)도 포함되어 있습니다. `.env`의 `PGDATABASE`/`PGUSER`/`PGPASSWORD`를 읽어 `postgres:18` 컨테이너를 띄우므로, 위 `docker run` 대신 `docker compose up -d`로 구성할 수도 있습니다. (단 compose는 볼륨명/PGDATA 경로가 위 예시와 다르므로 둘을 혼용하지 마세요.)

---

## 7단계. 스키마 적용 `[필수]`

데이터베이스 접속 상태를 확인하고 필요한 테이블을 마이그레이션합니다. 프로젝트 루트에서 아래 파이썬 인라인 스크립트를 실행합니다.

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import psycopg
import app.config.settings as cfg

schema = cfg.PGSCHEMA
migrations_dir = Path("db/migrations")

with psycopg.connect(
    host=cfg.PGHOST,
    port=cfg.PGPORT,
    dbname=cfg.PGDATABASE,
    user=cfg.PGUSER,
    password=cfg.PGPASSWORD,
    autocommit=True,
) as conn:
    with conn.cursor() as cur:
        for sql_path in sorted(migrations_dir.glob("*.sql")):
            sql_text = sql_path.read_text(encoding="utf-8").replace("auto_trading", schema)
            cur.execute(sql_text)
            print(f"Applied: {sql_path.name} -> {schema}")
PY
```

> [!NOTE]
> [db/migrations/](../db/migrations) 경로의 SQL 파일 내 `auto_trading` 스키마 이름이 [.env](../.env)에 명시된 `PGSCHEMA` 값으로 치환되어 순차 적용됩니다.

---

## 8단계. `grid.properties` 확인 `[필수]`

봇이 구동 시 로드할 그리드 설정 파일을 확인하고 조정합니다.

**기본 구성 예시 ([grid.properties](../grid.properties))**:
```properties
MIN_BUY_PRICE=1430
MAX_BUY_PRICE=1530
TOTAL_BUDGET_KRW=10000000
GRID_COUNT=10
TP_MODEL=k
TP_K_BASE=3.2
TP_K_FLOOR=3.0
```

> [!WARNING]
> - 위 값은 현재 `cfg.SYMBOL` 마켓(KRW-USDT) 기준의 예시이며, 실제 운영 값은 [grid.properties](../grid.properties) 파일을 직접 확인하세요. 마켓을 바꾸면 가격 스케일도 함께 맞춰야 합니다.
> - `MIN_BUY_PRICE`와 `MAX_BUY_PRICE`는 업비트 KRW 호가 단위에 일치해야 합니다.
> - 그리드 슬롯 계산을 위해 `GRID_COUNT` 혹은 `GRID_STEP_PCT` 중 **반드시 하나만** 명시해야 합니다.
> - `TOTAL_BUDGET_KRW`는 가동 예산이며, 하단 가중치 배분 규칙에 따라 상/중/하단 슬롯에 비례 배분됩니다.
> - [settings.py](../app/config/settings.py)의 `GRID_TP_K_BASE`와 [grid.properties](../grid.properties)의 `TP_K_BASE` 설정 값은 일치시켜 두는 것이 권장됩니다.

---

## 9단계. 비파괴 검증 `[필수]`

의존성 패키지와 테스트 스위트가 정상 동작하는지 확인합니다.
```bash
.venv/bin/python -c "import main"
.venv/bin/python -m unittest discover -s tests -v
```

> [!NOTE]
> `import main` 과정에서 에러가 없고 모든 단위 테스트(unittest)가 통과하면 런타임 환경이 정상 구성된 것입니다.
> - 단, PostgreSQL 연동 테스트는 `postgres`라는 이름의 Docker 컨테이너가 있어야 실행되며, 없으면 **에러 없이 자동 스킵(skip)** 됩니다(6단계에서 컨테이너를 `auto-postgres`로 만들면 이 테스트들은 스킵됨). 즉 "통과"만으로 DB 스키마까지 검증된 것은 아닙니다.
> - DB 스키마를 실제로 검증하려면 `PGPASSWORD` 등 PG 환경변수를 export한 뒤(또는 `set -a; . ./.env; set +a`) 테스트를 실행하세요.

---

## 10단계. 초기 그리드 반영 `[필수]`

설정된 [grid.properties](../grid.properties) 내용을 데이터베이스 그리드 테이블에 강제 주입합니다.
```bash
.venv/bin/python scripts/apply_grid_properties_to_postgres.py --force
```

현재 저장된 그리드 상태와 업비트 잔고 확인:
```bash
.venv/bin/python scripts/show_grid_state.py
.venv/bin/python main.py balance
```

> [!CAUTION]
> `--force` 플래그는 동일한 `STATE_BOT_KEY`를 가진 기존 그리드 상태를 **완전히 초기화하고 덮어씁니다**. 봇이 실제 운영 중일 때는 절대 단독 실행해선 안 됩니다.

---

## 11단계. 실행 `[필수]`

봇을 백그라운드로 구동하고 실시간 로그를 확인합니다.
```bash
PYTHON_BIN=.venv/bin/python ./run.sh
./tail-latest-log.sh
```

가동 중인 백그라운드 봇 프로세스 종료:
```bash
./stop.sh
```

---

## 12단계. 운영 체크 `[필수]`

- **주문 실행**: 실제 주문이 나가는 메인 루프는 [main.py](../main.py) 혹은 [run.sh](../run.sh)를 통해서만 가동됩니다.
- **실거래 가동 검증**: 실거래 실행 직전 업비트 API 키와 DB 테이블 정합성을 다시 한 번 점검하세요.
- **조회 명령어**: [show_grid_state.py](../scripts/show_grid_state.py)는 DB를 조회만 하는 안전한 Read-Only 스크립트입니다.
- **운영 중 덮어쓰기 주의**: [apply_grid_properties_to_postgres.py](../scripts/apply_grid_properties_to_postgres.py)의 `--force` 옵션은 가동 중인 봇의 매수 기록을 유실시킬 수 있습니다.

### 🔄 운영 서버 표준 배포 절차
1. `git fetch`
2. `./stop.sh` (봇 정지)
3. `git pull --ff-only origin main` (코드 업데이트)
4. `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh` (봇 재부팅)
5. `./tail-latest-log.sh` (정상 가동 로그 확인)

---

📚 **다음 단계**:
가본 설치와 동작 점검이 끝났다면 [operations.md](../docs/operations.md) 문서를 통해 실 운영 관리 및 손절(Stop-loss) 가이드를 이어서 살펴보세요.
