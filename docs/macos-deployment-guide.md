# macOS 설치/실행 가이드

이 문서는 새 macOS 시스템에 이 프로젝트를 설치하고,
Docker + PostgreSQL 기반으로 실행하는 절차를 정리한 가이드다.

기준 프로젝트 경로 예시:
```bash
~/auto
```

기준 운영 방식:
- 상태 저장: PostgreSQL
- 그리드 입력: `grid.properties`
- 그리드 반영: `scripts/apply_grid_properties_to_postgres.py`
- 봇 실행/종료: `./run.sh`, `./stop.sh`

---

## 1. 준비물

필수:
- macOS
- Docker Desktop for Mac
- Python 3.11+ 권장
- Git
- 업비트 API 키

권장:
- Homebrew

---

## 2. 기본 도구 설치

### 2-1. Homebrew 설치 확인
```bash
brew --version
```

없으면 설치:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2-2. Git 설치 확인
```bash
git --version
```

없으면:
```bash
brew install git
```

### 2-3. Python 설치 확인
```bash
python3 --version
```

없으면:
```bash
brew install python
```

---

## 3. Docker Desktop 설치

### 3-1. 설치
아래 중 하나:
- 공식 사이트에서 Docker Desktop for Mac 설치
- 또는 Homebrew Cask

```bash
brew install --cask docker
```

### 3-2. Docker 실행 확인
Docker Desktop 앱을 직접 켠 뒤:
```bash
docker --version
docker ps
```

정상적으로 컨테이너 목록이 나오면 된다.

---

## 4. 프로젝트 배치

원하는 위치에 프로젝트를 둔다.
예:
```bash
cd ~
git clone <레포주소> auto
cd ~/auto
```

레포가 아니라 파일 복사 방식이면 그냥 `/Users/<너계정>/auto` 식으로 두면 된다.

---

## 5. Python 가상환경 생성

macOS에서는 시스템 Python 대신 가상환경 사용을 권장한다.

```bash
cd ~/auto
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

앞으로 작업 전에 보통 이거 먼저:
```bash
cd ~/auto
source .venv/bin/activate
```

---

## 6. PostgreSQL 컨테이너 실행

예시:
```bash
docker run -d \
  --name auto-postgres \
  -e POSTGRES_DB=yangyag \
  -e POSTGRES_USER=yangyag \
  -e POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD \
  -p 5432:5432 \
  -v auto_postgres_data:/var/lib/postgresql/data \
  postgres:18
```

정상 확인:
```bash
docker ps
```

주의:
- `YOUR_STRONG_PASSWORD`는 실제 강한 비밀번호로 바꿔라.
- 이미 5432 포트를 다른 프로그램이 쓰면 포트를 바꿔야 한다.
  예: `-p 5433:5432`

---

## 7. DB 스키마 생성

프로젝트 루트에서:
```bash
cd ~/auto
source .venv/bin/activate
```

스키마 적용:
```bash
python3 - <<'PY'
from pathlib import Path
import psycopg

sql_text = Path('db/migrations/001_auto_trading_schema.sql').read_text(encoding='utf-8')
with psycopg.connect(
    host='127.0.0.1',
    port=5432,
    dbname='yangyag',
    user='yangyag',
    password='YOUR_STRONG_PASSWORD',
    autocommit=True,
) as conn:
    with conn.cursor() as cur:
        cur.execute(sql_text)
print('schema applied')
PY
```

포트를 바꿨으면 같이 바꿔라.

---

## 8. `.env` 파일 작성

프로젝트 루트 `~/auto/.env` 파일 생성:

```env
UPBIT_ACCESS_KEY=YOUR_UPBIT_ACCESS_KEY
UPBIT_SECRET_KEY=YOUR_UPBIT_SECRET_KEY

STATE_BACKEND=postgres
STATE_BOT_KEY=krw-btc-live

PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=yangyag
PGUSER=yangyag
PGPASSWORD=YOUR_STRONG_PASSWORD
PGSCHEMA=auto_trading
```

주의:
- 이 파일은 절대 외부에 공개하면 안 된다.
- 포트를 5433으로 열었으면 `PGPORT=5433`으로 맞춰라.

---

## 9. `grid.properties` 작성

프로젝트 루트 `~/auto/grid.properties`:

```properties
MIN_BUY_PRICE=91623000
MAX_BUY_PRICE=127886000
BUY_AMOUNT_KRW=200000
GRID_COUNT=20
SELL_PERCENT=5
```

의미:
- `MIN_BUY_PRICE`: 최하단 슬롯 buy_price
- `MAX_BUY_PRICE`: 최상단 슬롯 buy_price
- `BUY_AMOUNT_KRW`: 슬롯별 목표 매수금액
- `GRID_COUNT`: 슬롯 개수
- `SELL_PERCENT`: 매도 퍼센트, `5`는 `5%`를 뜻한다

중요:
- `MIN_BUY_PRICE`, `MAX_BUY_PRICE`는 업비트 호가 단위에 맞는 값이어야 한다.
- 틱 단위에 안 맞으면 스크립트가 에러를 낸다.

---

## 10. 그리드를 PostgreSQL에 반영

프로젝트 루트에서:
```bash
cd ~/auto
source .venv/bin/activate
python3 scripts/apply_grid_properties_to_postgres.py --force
```

또는 scripts 폴더 안에서:
```bash
cd ~/auto/scripts
../.venv/bin/python3 ./apply_grid_properties_to_postgres.py --force
```

정상 출력 예시:
```text
상태: 성공
bot_key: krw-btc-live
symbol: KRW-BTC
rows: 20
...
```

---

## 11. 비파괴 검증

### 11-1. import 확인
```bash
cd ~/auto
source .venv/bin/activate
python3 -c "import main"
```

### 11-2. 테스트
```bash
python3 -m unittest discover -s tests -v
```

### 11-3. 업비트 KRW 잔고 확인
```bash
python3 main.py balance
```

---

## 12. 실행

프로젝트 루트에서:
```bash
cd ~/auto
source .venv/bin/activate
./run.sh
```

정상 확인:
```bash
ps -eo pid,args | grep '[p]ython3 /Users/.*/auto/main.py'
```
또는 더 단순히:
```bash
cat .auto-trading.pid
```

로그 확인:
```bash
tail -f logs/trading-$(date +%F).log
```

정상 시작 시 기대 로그 예:
- `=== 그리드 자동매매 시작 ===`
- `postgres 단일 실행 락 획득: bot_key=...`
- `심볼: KRW-BTC | 전체 슬롯: ...`
- `현재가: ...`

---

## 13. 종료

```bash
cd ~/auto
./stop.sh
```

---

## 14. 자주 쓰는 명령

### 그리드 다시 반영
```bash
cd ~/auto
source .venv/bin/activate
python3 scripts/apply_grid_properties_to_postgres.py --force
```

### DB 상태를 파일로 백업 export
```bash
python3 scripts/export_postgres_grid.py
```

### 로그 보기
```bash
tail -n 100 logs/trading-$(date +%F).log
```

### 실시간 로그
```bash
tail -f logs/trading-$(date +%F).log
```

---

## 15. macOS 주의사항

### Docker Desktop이 안 떠 있으면
- `docker ps` 자체가 실패한다.
- 먼저 Docker Desktop 앱이 켜져 있어야 한다.

### Apple Silicon(M1/M2/M3)
- 보통 그대로 동작한다.
- `postgres:18`도 일반적으로 문제 없다.

### `run.sh`에서 가상환경 Python을 쓰고 싶으면
기본은 `python3`를 쓴다.
가상환경 Python을 강제로 쓰려면:
```bash
cd ~/auto
PYTHON_BIN="$PWD/.venv/bin/python3" ./run.sh
```

이 방식이 제일 안전하다.

---

## 16. 추천 실행 순서

처음 한 번은 아래 순서 그대로 하면 된다.

```bash
cd ~/auto
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
docker run -d \
  --name auto-postgres \
  -e POSTGRES_DB=yangyag \
  -e POSTGRES_USER=yangyag \
  -e POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD \
  -p 5432:5432 \
  -v auto_postgres_data:/var/lib/postgresql/data \
  postgres:18
```

```bash
cd ~/auto
source .venv/bin/activate
python3 - <<'PY'
from pathlib import Path
import psycopg
sql_text = Path('db/migrations/001_auto_trading_schema.sql').read_text(encoding='utf-8')
with psycopg.connect(host='127.0.0.1', port=5432, dbname='yangyag', user='yangyag', password='YOUR_STRONG_PASSWORD', autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute(sql_text)
print('schema applied')
PY
```

`.env`, `grid.properties` 작성 후:
```bash
python3 scripts/apply_grid_properties_to_postgres.py --force
python3 -c "import main"
python3 main.py balance
PYTHON_BIN="$PWD/.venv/bin/python3" ./run.sh
```

---

## 17. 마지막 주의

이 프로그램은 실거래 봇이다.
즉:
- API 키가 맞고
- `./run.sh`를 실행하면
- 실제 주문이 나갈 수 있다.

그래서 첫 실행 전에는 반드시:
- `.env` 값 확인
- `grid.properties` 값 확인
- `python3 main.py balance` 확인
- 로그 모니터링 준비
를 하고 들어가는 게 맞다.
