# AGENTS.md

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

## 작업 파이프라인
- 기본 구현 흐름은 `Planner -> Generator -> Evaluator` 다.
- 수식, 계산, 전략 로직, 예산 분배, TP/리스크 규칙 같은 로직 변경이 포함되면 흐름은 `Planner -> Math Expert -> Generator -> Evaluator` 로 바꾼다.
- 비단순 작업은 가능하면 각 역할을 실제로 분리된 에이전트로 나눠서 수행하고, 단순 작업도 최소한 같은 순서의 점검 흐름을 유지한다.

### Planner
- 요청을 기능 단위로 쪼개고 범위와 완료 기준을 먼저 고정한다.
- 영향 파일과 선행 인터페이스를 먼저 확인한다.
- 실거래 부작용 없는 검증 우선 원칙을 유지한다.
- 작업에 수식, 계산, 전략 로직, 예산 분배, TP/리스크 규칙 변경이 들어가는지 먼저 판별하고, 해당되면 `Math Expert` 단계로 넘긴다.

### Math Expert
- `Planner`가 세운 계획에 포함된 수식, 계산식, 기준값, 예산 분배, TP 규칙, 리스크 계산, 트리거 조건이 수학적으로 맞는지 검증한다.
- 핵심은 코드 스타일이 아니라 로직의 정합성, 단위 일관성, 경계 조건, 계산 방향이 맞는지 확인하는 것이다.
- 검증 대상 작업은 전략 로직 변경, 수식 추가/변경, 예산 배분 변경, TP/리스크 규칙 변경, 재고 비율 계산 변경이다.
- 문제가 없을 때만 `Generator` 단계로 넘긴다.
- 수학적으로 틀리거나 불완전하면 즉시 `Planner` 단계로 되돌리고, 수정된 계획이 다시 `Math Expert` 검토를 거치게 한다.
- 이 역할은 항상 최신 모델을 쓰고, reasoning effort 는 항상 `xhigh` 로 고정한다.

### Generator
- `Planner`가 고정한 범위와 완료 기준을 바꾸지 않고 구현한다.
- `Math Expert` 검증 대상 작업은 승인 전에는 구현하지 않는다.
- 즉시 다음 행동을 막는 핵심 작업은 메인 세션이 직접 처리하고, 독립적인 보조 작업만 분리한다.
- 문서나 설정 의미가 달라졌다면 관련 문서를 함께 맞춘다.

### Evaluator
- 구현 후 반드시 별도 검토 관점으로 한 번 더 점검한다.
- 핵심은 “돌아가는가”가 아니라 “운영 중 깨질 지점이 남아 있는가”다.
- 회귀 위험, 민감정보 노출, 실거래 부작용 가능성을 다시 확인한다.

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

## 자격증명 / 민감정보 원칙
- API 키는 환경변수 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`로만 주입한다.
- PostgreSQL 접속정보도 프로젝트 루트 `.env` 또는 EC2 `/home/ubuntu/auto/.env`로만 관리한다.
- 민감정보를 문서, 샘플 파일, 커밋에 복제하지 않는다.
