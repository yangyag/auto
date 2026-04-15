# PostgreSQL 운영 체크리스트

## 현재 기준
- 운영 저장소는 PostgreSQL 전용이다.
- `grid.properties`로 생성한 그리드가 PostgreSQL에 저장된다.
- 상태 확인과 export는 보조 도구로만 사용한다.

## 시작 전 확인
1. 업비트 open order 가 0개인지 확인한다.
2. `python3 -m unittest discover -s tests -v` 가 통과하는지 확인한다.
3. `.env`에 `STATE_BOT_KEY`와 PostgreSQL 접속 정보가 있는지 확인한다.
4. `python3 scripts/show_grid_state.py`로 현재 DB snapshot을 확인한다.

## 권장 순서
1. 현재 실행 중 봇 상태 확인
   - `ps -eo pid,args | grep '[p]ython3 /home/yangyag/auto/main.py'`
2. open order 0개 확인
   - 현재 코드는 개별 order 상태 조회는 가능하지만 거래소 전체 open order 백필은 없다.
   - 따라서 실제 재시작은 미체결 주문이 없는 타이밍에서만 진행한다.
3. 필요 시 그리드 재생성
   - `python3 scripts/apply_grid_properties_to_postgres.py --force`
4. 프로세스 재시작
   - `./stop.sh`
   - `./run.sh`
5. 시작 직후 로그 확인
   - postgres 단일 실행 락 획득 로그가 있는지
   - bot_key / grid summary / 미체결 주문 복구 로그가 의도와 맞는지

## 운영상 주의
- `scripts/export_postgres_grid.py` 기본 출력 파일은 `grid.postgres-export.txt` 이다.
- `scripts/show_grid_state.py`는 읽기 전용이다.
- postgres backend 는 단일 실행 락을 사용하므로 같은 `STATE_BOT_KEY` 로 2개 프로세스를 동시에 띄우면 안 된다.
- postgres backend 는 빈 snapshot 으로 시작하지 않도록 fail-fast 한다. bot_key/schema 를 잘못 주면 시작 시 에러가 나야 정상이다.
