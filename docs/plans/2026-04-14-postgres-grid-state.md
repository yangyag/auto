# PostgreSQL 상태 저장 전환 구현 계획

이 문서는 file backend 에서 PostgreSQL 전용 운영으로 넘어가던 당시의 계획 기록이다. 현재 운영 기준 문서가 아니다.

> For Hermes: Use subagent-driven-development skill to implement this plan task-by-task.

목표: `grid.txt` 기반 상태 저장을 PostgreSQL 기반으로 전환하고, pending/open order까지 DB에 저장해 재시작 후에도 안전하게 복구되도록 만든다.

아키텍처:
- 도메인 상태(`GridState`)와 영속화 계층을 분리한다.
- 저장소 인터페이스를 도입해 file/postgres 백엔드를 모두 지원하되, 최종 운영은 postgres primary로 간다.
- 체결/취소/관리자 수정은 DB transaction + version 증가 + revision 기록으로 일관성 있게 처리한다.

기술 스택:
- Python
- PostgreSQL (docker 컨테이너 사용)
- psycopg 3
- unittest 기반 기존 테스트 확장

사용자 결정사항:
- pending/open order도 이번 마이그레이션에 포함
- 향후 수동 수정은 grid.txt가 아니라 DB 직접 수정(에이전트 경유)
- 최종 운영은 postgres primary, grid.txt는 더 이상 source of truth가 아님

---

## Task 1: 저장소 경계 정의

목표: 현재 `GridState`의 파일 I/O 책임을 저장소 계층으로 분리할 인터페이스를 만든다.

파일:
- Create: `storage/__init__.py`
- Create: `storage/interfaces.py`
- Test: `tests/test_state_factory.py`

세부 작업:
1. `storage/interfaces.py`에 다음 개념을 정의한다.
   - `GridSnapshot` 또는 동등한 dataclass
   - `GridStateRepository`
   - `PendingOrderRepository`
   - 저장소가 반환하는 version/revision 메타데이터
2. `GridStateRepository`는 최소한 아래 책임을 가진다.
   - 상태 로드
   - 상태 전체 저장 또는 슬롯 갱신 반영
   - 외부 변경(version) 확인
3. `PendingOrderRepository`는 최소한 아래 책임을 가진다.
   - open order 저장
   - 상태 조회
   - fill/cancel 반영
   - 재시작 복구용 open order 목록 반환
4. 인터페이스 수준 테스트를 추가한다.
   - 최소한 팩토리/인터페이스 인스턴스 생성 가능 여부 확인

검증:
- `python3 -m unittest tests.test_state_factory -v`

---

## Task 2: GridState를 도메인 전용 객체로 정리

목표: `core/grid.py`에서 직접 파일을 읽고 쓰는 책임을 제거한다.

파일:
- Modify: `core/grid.py`
- Test: `tests/test_grid_reload.py`

세부 작업:
1. `GridState.__init__()`의 즉시 파일 로드 책임을 제거한다.
2. `load()`, `save()`, `reload_if_changed()` 같은 파일 중심 메서드를 제거하거나 repository 기반 흐름으로 대체 가능한 형태로 축소한다.
3. 아래 도메인 동작은 유지한다.
   - `total_inventory`
   - `total_allocated_budget`
   - `apply_buy()`
   - `apply_sell()`
   - `summary()`
4. 필요한 경우 `from_rows()`는 유지하되 순수 생성기로 정리한다.
5. 테스트를 repository/version 기반 의미에 맞게 수정한다.

검증:
- `python3 -m unittest tests.test_grid_reload -v`

---

## Task 3: 파일 백엔드 저장소 구현

목표: 기존 동작을 깨지 않도록 file repository로 현재 `grid.txt` semantics를 먼저 보존한다.

파일:
- Create: `storage/file_grid_repository.py`
- Create: `storage/factory.py`
- Test: `tests/test_file_grid_repository.py`

세부 작업:
1. `grid.txt` 파싱/저장 로직을 file repository로 이동한다.
2. file repository는 기존 포맷을 그대로 유지한다.
   - `Grid3 SYMBOL`
   - 각 슬롯 줄
   - 마지막 `테이블 총재고` 줄
3. 외부 변경 감지는 기존 mtime 기반 semantics를 그대로 제공한다.
4. `storage/factory.py`에서 설정에 따라 저장소를 생성하는 팩토리를 만든다.

검증:
- `python3 -m unittest tests.test_file_grid_repository -v`
- `python3 -m unittest tests.test_grid_builder tests.test_grid_reload -v`

---

## Task 4: main.py를 저장소 중심으로 리팩터링

목표: 메인 루프가 파일 경로 대신 저장소 인터페이스를 통해 상태를 읽고 저장하게 만든다.

파일:
- Modify: `main.py`
- Modify: `strategy/grid_strategy.py`
- Test: `tests/test_order_sync.py`
- Test: `tests/test_main_balance.py`

세부 작업:
1. `main.py` 시작 시 저장소에서 snapshot을 읽어 `GridState`를 구성한다.
2. `refresh_grid_state_if_changed()`는 repository version/mtime check를 사용하도록 바꾼다.
3. `strategy/grid_strategy.py::apply_filled_order()`에서 직접 `self.grid.save()`를 호출하지 않게 한다.
4. `main.py`가 fill/cancel 후 명시적으로 저장소를 호출해 상태를 반영하게 한다.
5. 기존 리스크 체크/체결 동기화 흐름은 유지한다.

검증:
- `python3 -m unittest tests.test_order_sync tests.test_main_balance -v`
- `python3 -c "import main"`

---

## Task 5: pending/open order 영속화 추가

목표: 재시작 후에도 미체결 주문을 이어받을 수 있게 한다.

파일:
- Modify: `main.py`
- Create: `storage/postgres_order_repository.py` 또는 file stub 대응 코드
- Test: `tests/test_order_sync.py`

세부 작업:
1. 주문 접수 시 pending/open order를 저장소에 기록한다.
2. fill/cancel 시 저장소 상태를 갱신한다.
3. 봇 시작 시 open orders를 읽어 `pending_orders` 메모리 상태를 복구한다.
4. 동일 order_id에 대한 중복 반영이 idempotent 하도록 설계한다.
5. 가능하면 slot 단위 중복 open order 방지도 저장소 제약에 포함한다.

검증:
- `python3 -m unittest tests.test_order_sync -v`

---

## Task 6: PostgreSQL 스키마 추가

목표: shared postgres 안에 bot 전용 schema와 테이블을 만든다.

파일:
- Create: `db/migrations/001_auto_trading_schema.sql`
- Test: `tests/test_postgres_grid_repository.py`
- Test: `tests/test_postgres_order_repository.py`

세부 작업:
1. dedicated schema를 만든다. 권장 이름: `auto_trading`
2. 최소 테이블:
   - `bot_state`
   - `grid_slots`
   - `grid_revisions`
   - `orders`
3. numeric precision은 BTC/KRW Decimal을 손실 없이 저장할 수 있게 잡는다.
4. `bot_state.version`을 외부 변경 감지용으로 사용한다.
5. `orders`에는 open order uniqueness 제약을 넣는다.

검증:
- migration SQL을 postgres 컨테이너에 적용
- `python3 -m unittest tests.test_postgres_grid_repository tests.test_postgres_order_repository -v`

---

## Task 7: PostgreSQL 저장소 구현

목표: postgres primary 저장소를 구현한다.

파일:
- Create: `storage/postgres_grid_repository.py`
- Create: `storage/postgres_order_repository.py`
- Modify: `storage/factory.py`
- Modify: `requirements.txt`

세부 작업:
1. `psycopg[binary]` 의존성을 추가한다.
2. grid snapshot load/save를 transaction으로 구현한다.
3. 저장 시:
   - 슬롯 갱신
   - revision 기록
   - version 증가
   를 원자적으로 처리한다.
4. 외부 변경 감지는 `bot_state.version` 기반으로 구현한다.
5. 재시작 복구용 open orders load를 구현한다.

검증:
- `python3 -m unittest tests.test_postgres_grid_repository tests.test_postgres_order_repository -v`

---

## Task 8: 설정/환경변수 추가

목표: postgres primary 운영에 필요한 설정을 코드에서 읽게 한다.

파일:
- Modify: `config/settings.py`
- Test: `tests/test_settings_env.py`

세부 작업:
1. 아래 설정 추가
   - `STATE_BACKEND`
   - `STATE_BOT_KEY`
   - `PGHOST`
   - `PGPORT`
   - `PGDATABASE`
   - `PGUSER`
   - `PGPASSWORD`
   - `PGSCHEMA`
2. `.env` 로딩 흐름과 충돌 없이 동작하게 한다.
3. 기본값은 안전하게 잡되, postgres primary 의도를 반영한다.

검증:
- `python3 -m unittest tests.test_settings_env -v`

---

## Task 9: grid.txt → PostgreSQL 마이그레이션 도구 추가

목표: 현재 운영 그리드를 DB로 안전하게 옮긴다.

파일:
- Create: `scripts/migrate_grid_to_postgres.py`
- Create: `scripts/export_postgres_grid.py`
- Create: `scripts/compare_grid_sources.py`
- Test: `tests/test_grid_migration_script.py`

세부 작업:
1. importer는 현재 `grid.txt`를 읽어 DB snapshot 1회 적재 가능해야 한다.
2. exporter는 DB 상태를 사람이 읽을 수 있는 grid.txt 형태로 뽑을 수 있어야 한다.
3. compare 스크립트는 file vs DB 상태를 비교해 차이를 보여줘야 한다.
4. importer는 force 여부 없이 기존 bot_key를 덮어쓰지 않게 한다.

검증:
- `python3 -m unittest tests.test_grid_migration_script -v`

---

## Task 10: 단일 실행자 보장 및 컷오버 안전장치

목표: postgres backend에서 중복 봇 실행을 막고, 장애 시 fail-closed 하게 만든다.

파일:
- Modify: `main.py`
- Test: `tests/test_postgres_grid_repository.py`
- Test: `tests/test_order_sync.py`

세부 작업:
1. postgres advisory lock 또는 동등한 메커니즘으로 single-writer를 구현한다.
2. DB 연결 실패/저장 실패 시 새 주문은 막도록 한다.
3. version conflict가 발생하면 reload 후 재평가하도록 한다.
4. 체결 반영 중 저장 실패 시 중복 반영 방지 로직을 확인한다.

검증:
- 동시 실행/락 테스트
- DB 실패 상황 테스트

---

## Task 11: 전체 회귀 테스트 및 운영 검증

목표: 기존 동작과 새 postgres 동작이 모두 요구사항을 만족하는지 확인한다.

파일:
- Modify as needed: 테스트 파일들
- Update: `docs/current-status.md`

세부 작업:
1. 전체 테스트 실행
2. 현재 실제 `grid.txt`를 DB에 import 후 compare 검증
3. open order 0개 여부 확인 스크립트/절차 정리
4. `stop.sh` → 마이그레이션 → postgres primary 재기동 절차 문서화

검증 명령:
- `python3 -m unittest discover -s tests -v`
- `python3 -c "import main"`
- 필요 시 postgres 연결 확인 명령

---

## 컷오버 원칙

1. 구현 완료 전에는 live process를 건드리지 않는다.
2. 최종 전환 직전 아래를 확인한다.
   - open order 0개
   - DB import 결과와 기존 grid snapshot 일치
   - 테스트 통과
3. 그 다음에만
   - `./stop.sh`
   - postgres primary 설정 반영
   - 재시작
4. 재시작 직후에는
   - backend 종류
   - bot_key
   - version
   - open order 복구 수
   - 현재 그리드 요약
   로그를 반드시 확인한다.
