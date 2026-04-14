# PostgreSQL 컷오버 체크리스트

## 현재 상태
- live bot 는 여전히 file backend (`grid.txt`) 기준으로 실행 중이다.
- PostgreSQL 저장소 코드/마이그레이션/검증 테스트는 준비되었다.
- cutover 전까지 `STATE_BACKEND` 기본값은 `file` 로 유지한다.

## 절대 조건
1. `./stop.sh` 실행 전 업비트 open order 가 0개여야 한다.
2. cutover 직전의 `grid.txt`와 DB import 결과가 동일해야 한다.
3. `python3 -m unittest discover -s tests -v` 가 통과해야 한다.
4. `STATE_BACKEND=postgres` 와 DB 접속 환경변수가 준비되어 있어야 한다.

## 권장 순서
1. 현재 실행 중 봇 상태 확인
   - `ps -eo pid,args | grep '[p]ython3 /home/yangyag/auto/main.py'`
2. open order 0개 확인
   - 현재 코드는 개별 order 상태 조회는 가능하지만 exchange 전체 open order backfill 은 없다.
   - 따라서 실제 cutover 는 미체결 주문이 없는 타이밍에서만 진행한다.
3. cutover 직전 `grid.txt` 백업
   - `cp -f grid.txt grid.txt.bak.$(date +%Y%m%d-%H%M%S)`
4. postgres에 마지막으로 쓸 그리드 상태를 준비
   - 지금은 `grid.properties` 기반 운영이므로 필요 시 `python3 scripts/apply_grid_properties_to_postgres.py --force` 로 DB 그리드를 최신값으로 덮어쓴다.
5. 기존 프로세스 종료
   - `./stop.sh`
6. postgres backend 환경 반영
   - `STATE_BACKEND=postgres`
   - `STATE_BOT_KEY=krw-btc-live` (예시)
   - `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSCHEMA` 설정
8. 새 프로세스 시작
   - `./run.sh`
9. 시작 직후 로그 확인
   - backend 가 postgres 인지
   - 단일 실행 락 획득 로그가 있는지
   - bot_key / grid summary / 미체결 주문 복구 로그가 의도와 맞는지

## 롤백
1. 새 postgres backend 프로세스 중지
   - `./stop.sh`
2. 필요 시 DB 상태 export
   - `python3 scripts/export_postgres_grid.py --output grid.postgres-rollback.txt --bot-key $STATE_BOT_KEY --schema $PGSCHEMA --host $PGHOST --port $PGPORT --dbname $PGDATABASE --user $PGUSER --password $PGPASSWORD`
3. `STATE_BACKEND=file` 로 되돌림
4. 마지막으로 검증된 `grid.txt` 백업본 복원
5. `./run.sh` 로 file backend 재기동

## 운영상 주의
- `scripts/export_postgres_grid.py` 기본 출력 파일은 `grid.postgres-export.txt` 이다. live `grid.txt` 덮어쓰지 않도록 했다.
- postgres backend 는 단일 실행 락을 사용하므로 같은 `STATE_BOT_KEY` 로 2개 프로세스를 동시에 띄우면 안 된다.
- postgres backend 는 빈 snapshot 으로 시작하지 않도록 fail-fast 한다. bot_key/schema 를 잘못 주면 시작 시 에러가 나야 정상이다.
