# advisor

이 문서는 현재 운영 기준만 남긴 요약이다.

## 핵심 결론

- TP 기준은 `k-only`로 둔다.
- 기본값은 `TP_MODEL=k`, `TP_K_BASE=9.0`, `TP_K_FLOOR=7.0` 이다.
- `main.py init-grid`와 `grid.properties`는 같은 `TOTAL_BUDGET_KRW` + `GRID_COUNT` 총예산 계약을 쓴다.
- BUY 체결이 확인되면 해당 슬롯의 TP SELL pending 주문을 즉시 만든다.
- `cancelled` 이면서 `executed_volume > 0` 인 주문은 부분 체결로 보고 상태를 반영한다.
- 매수 리스크 계산에는 수수료 버퍼를 포함한다.
- 전체 예산 상한은 명시적으로 둔다.
- 브레이크아웃 가드는 데이터 불안정 시 신규 매수를 막는 fail-close로 둔다.

## 운영 우선순위

1. `TP_MODEL=k` 외의 설명은 붙이지 않는다.
2. 신규 그리드는 `TP_K_BASE=9.0`, `TP_K_FLOOR=7.0` 기준으로 맞춘다.
3. 체결 직후 TP SELL을 생성해 폴링 지연을 줄인다.
4. 부분 체결 취소는 수량 단위로 반영해서 잔고와 상태가 어긋나지 않게 한다.
5. `UPBIT_FEE_RATE`와 별도 버퍼를 합쳐 주문 가능 금액을 계산한다.
6. `TOTAL_BUDGET_KRW`, `MAX_TOTAL_BUDGET_KRW`, `MAX_OPERATING_BUDGET_KRW` 를 구분해서 상한과 입력 예산을 고정한다.
7. `BREAKOUT_GUARD_FAIL_OPEN=False` 로 두고, 조회 실패 시 신규 매수를 멈춘다.

## 정리

현재 기준에서 중요한 건 매도 폭을 일관되게 `k`로 관리하고, `init-grid`와 `grid.properties`의 총예산 계약을 같은 기준으로 보는 것이다. 그 위에 체결 직후 TP SELL, 부분 체결 취소 처리, 수수료 버퍼, 예산 상한, fail-close를 더해 실거래 사고를 막는 쪽으로 맞춘다.
