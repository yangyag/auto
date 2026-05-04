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
- 테스트 로그가 같은 날짜 파일에 남을 수 있으므로 로거 이름 `__main__` / `main`도 함께 확인한다.
- 실거래 주문이 발생할 수 있는 루프 실행은 명시적으로 필요할 때만 한다.

## 주문 관련 용어
- `orders` 테이블의 `quantity` 컬럼은 최초 발주량이다. 부분 체결 시 실제 체결량과 다를 수 있으므로 실 체결량은 `GridState.held_qty`를 참조한다. 사고 분석 시 두 값을 함께 본다.

## 라이브 예산 조정 비단조성 주의
- `scripts/adjust_budget_live.py`의 `r_lower`는 현재가에 의존한다. 동일 `--target-lower-budget X` 입력이라도 시장 위치가 바뀌면 implicit 총예산이 달라진다. 비단조 동작 자체는 설계 정상이지만, 실행 시점을 의식하고 여러 번 실행 시 누적 효과를 고려해야 한다.

## 자격증명 / 민감정보 원칙
- API 키는 환경변수 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`로만 주입한다.
- PostgreSQL 접속정보도 프로젝트 루트 `.env` 또는 EC2 `/home/ubuntu/auto/.env`로만 관리한다.
- 민감정보를 문서, 샘플 파일, 커밋에 복제하지 않는다.
