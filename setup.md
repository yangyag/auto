# setup.md

이 문서는 이 저장소를 **git clone 한 직후** 처음 설치하고, PostgreSQL 기반으로 초기 실행 가능한 상태까지 만드는 절차를 정리한 가이드다.

문서 역할:
- 프로그램 로직 설명은 `README.md`
- EC2, git, 배포, 운영 인프라는 `AGENTS.md`

기준 운영 방식:
- 거래소: 업비트 `KRW-BTC`
- 상태 저장: PostgreSQL
- 그리드 입력: `grid.properties`
- 그리드 반영: `scripts/apply_grid_properties_to_postgres.py`
- 봇 실행/종료: `./run.sh`, `./stop.sh`

## 1. 준비물

필수:
- Git
- Python 3.11+
- PostgreSQL 접속 정보
- 업비트 API 키

선택:
- `uv` (`python3 -m venv .venv` 가 실패할 때 사용)
- Docker (`postgres:18` 로 로컬 PostgreSQL을 빠르게 띄우고 싶을 때)

## 2. 저장소 받기

```bash
git clone git@github.com:yangyag/auto.git
cd auto
```

HTTPS를 쓰면:

```bash
git clone https://github.com/yangyag/auto.git
cd auto
```

## 3. 가상환경 생성

기본 경로:

```bash
python3 -m venv .venv
```

`ensurepip` 오류로 실패하면:

```bash
~/.local/bin/uv venv --clear .venv
~/.local/bin/uv pip install --python .venv/bin/python pip
```

## 4. 의존성 설치

```bash
.venv/bin/python -m pip install -r requirements.txt
```

## 5. `.env` 작성

샘플 파일을 복사한 뒤 실제 값으로 채운다.

```bash
cp .env_sample .env
```

최소 예시:

```env
UPBIT_ACCESS_KEY=YOUR_UPBIT_ACCESS_KEY
UPBIT_SECRET_KEY=YOUR_UPBIT_SECRET_KEY

STATE_BOT_KEY=krw-btc-live

PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=yangyag
PGUSER=yangyag
PGPASSWORD=YOUR_DB_PASSWORD
PGSCHEMA=auto_trading
```

주의:
- `config/settings.py`는 프로젝트 루트 `.env`를 읽는다.
- 같은 서버에 `/home/ubuntu/llm.env` 가 있어도 이 저장소 설정 파일이 아니다.
- EC2 운영 서버 기준 자동매매 `.env` 경로는 `/home/ubuntu/auto/.env` 다.

## 6. PostgreSQL 준비

이미 PostgreSQL이 있으면 이 단계는 건너뛰고 `.env`만 맞춘다.

로컬 Docker 예시:

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

## 7. 스키마 적용

프로젝트 루트에서:

```bash
.venv/bin/python - <<'PY'
import os
from pathlib import Path

import psycopg

schema = os.getenv("PGSCHEMA", "auto_trading")
migrations_dir = Path("db/migrations")

with psycopg.connect(
    host=os.getenv("PGHOST", "127.0.0.1"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "yangyag"),
    user=os.getenv("PGUSER", "yangyag"),
    password=os.getenv("PGPASSWORD", ""),
    autocommit=True,
) as conn:
    with conn.cursor() as cur:
        for sql_path in sorted(migrations_dir.glob("*.sql")):
            sql_text = sql_path.read_text(encoding="utf-8").replace("auto_trading", schema)
            cur.execute(sql_text)
            print(f"applied: {sql_path.name} -> {schema}")
PY
```

## 8. `grid.properties` 확인

기본 예시:

```properties
MIN_BUY_PRICE=98000000
MAX_BUY_PRICE=121000000
BUY_AMOUNT_KRW=25000
GRID_COUNT=96
SELL_PERCENT=3.2
TP_MODEL=k
TP_K_BASE=11.0
TP_K_FLOOR=8.0
```

주의:
- `MIN_BUY_PRICE`, `MAX_BUY_PRICE`는 업비트 KRW 호가 단위에 맞아야 한다.
- `grid.properties` 경로는 총예산 `BUY_AMOUNT_KRW * GRID_COUNT` 를 가중 배분한다.
- `config/settings.py`의 `GRID_TP_K_BASE` 와 `grid.properties`의 `TP_K_BASE` 는 맞춰 두는 것이 안전하다.

## 9. 비파괴 검증

```bash
.venv/bin/python -c "import main"
.venv/bin/python -m unittest discover -s tests -v
```

## 10. 초기 그리드 반영

```bash
.venv/bin/python scripts/apply_grid_properties_to_postgres.py --force
```

상태 확인:

```bash
.venv/bin/python scripts/show_grid_state.py
.venv/bin/python main.py balance
```

## 11. 실행

```bash
PYTHON_BIN=.venv/bin/python ./run.sh
./tail-latest-log.sh
```

종료:

```bash
./stop.sh
```

## 12. 운영 체크

- 실제 주문 루프는 `.venv/bin/python main.py` 또는 `./run.sh` 경로에서만 돈다.
- 실거래 전에는 업비트 API 키와 PostgreSQL 접속 정보가 맞는지 먼저 확인한다.
- `scripts/show_grid_state.py`는 읽기 전용이다.
- `scripts/apply_grid_properties_to_postgres.py --force` 는 같은 `STATE_BOT_KEY` 상태를 전체 덮어쓴다.
- 운영 서버 배포는 `git fetch` -> `./stop.sh` -> `git pull --ff-only origin main` -> `PYTHON_BIN=/home/ubuntu/auto/.venv/bin/python ./run.sh` 순서가 기본이다.
