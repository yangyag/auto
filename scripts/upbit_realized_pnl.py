#!/usr/bin/env python3
"""업비트 실현 손익 분석 (KRW-BTC, read-only).

매칭 방식: 슬롯 1:1 매칭. identifier 의 슬롯 번호로 BUY ↔ SELL 짝지음.
글로벌 FIFO 와 의도적으로 다른 결과를 생산 (봇 슬롯 단위 매핑 의미).

identifier 형식: '{STATE_BOT_KEY}-{buy|sell}-{slot}-{ms}-{hex12}'
발급 지점: main.py:ensure_order_identifier() (line 110-118).
STATE_BOT_KEY 는 cfg.STATE_BOT_KEY 로 동적 참조 (운영 환경별 호환).

한계: 같은 millisecond 의 BUY/SELL trade 가 슬롯 안에서 동률일 때 uuid
tie-break 로 SELL 이 먼저 처리될 가능성 (운영상 거의 불가능, 안내 노트).

사용법:
    .venv/bin/python scripts/upbit_realized_pnl.py [--from YYYY-MM-DD] [--to YYYY-MM-DD]
        [--period daily|weekly|monthly|yearly|all] [--market KRW-BTC]
        [--reset-sell-uuid UUID]

기본값:
    --from  : 오늘 기준 90일 전
    --to    : 오늘
    --period: all  (daily/weekly/monthly/yearly/ALL 5개 섹션 모두 출력)
    --market: KRW-BTC
"""
import argparse
import hashlib
import re
import sys
import time
import uuid
import warnings
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlencode
from zoneinfo import ZoneInfo

import jwt
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app.config.settings as cfg

try:
    from jwt.warnings import InsecureKeyLengthWarning
except ImportError:
    InsecureKeyLengthWarning = Warning

warnings.filterwarnings("ignore", category=InsecureKeyLengthWarning)
warnings.filterwarnings(
    "ignore",
    message=r"The HMAC key is .* below the minimum recommended length of 64 bytes for SHA512\.",
    category=Warning,
)

# ── 슬롯 identifier 파싱 ──────────────────────────────────────


def _slot_pattern() -> re.Pattern:
    r"""cfg.STATE_BOT_KEY 를 동적으로 참조해 슬롯 패턴 컴파일.

    운영 환경: STATE_BOT_KEY="krw-btc-live" 이면
    패턴: ^krw-btc-live-(buy|sell)-(\d+)-
    """
    return re.compile(rf'^{re.escape(cfg.STATE_BOT_KEY)}-(buy|sell)-(\d+)-')


def _reset_sell_pattern() -> re.Pattern:
    return re.compile(rf'^{re.escape(cfg.STATE_BOT_KEY)}-reset-sell-')


SLOT_PATTERN = _slot_pattern()
RESET_SELL_PATTERN = _reset_sell_pattern()


def extract_slot_index(identifier: str | None) -> int | None:
    """identifier 에서 슬롯 번호 추출.

    형식: '{STATE_BOT_KEY}-{buy|sell}-{slot}-{ms}-{hex12}'
    발급 지점: main.py:ensure_order_identifier()
    """
    if not identifier:
        return None
    m = SLOT_PATTERN.match(identifier)
    if not m:
        return None
    return int(m.group(2))


def is_reset_sell_order(order: dict, reset_sell_uuids: set[str]) -> bool:
    """reset liquidation SELL 여부를 판정한다."""
    if order.get("side") != "ask":
        return False
    if order.get("uuid") in reset_sell_uuids:
        return True
    identifier = order.get("identifier")
    return bool(identifier and RESET_SELL_PATTERN.match(identifier))


# ── 상수 ─────────────────────────────────────────────────────
BASE_URL = "https://api.upbit.com"
KST = ZoneInfo("Asia/Seoul")
RATE_LIMIT_SLEEP_SEC = 0.05   # 50ms, rate-limit 안전마진
WINDOW_DAYS = 7               # closed orders 분할 조회 윈도우 (일)
DEFAULT_MARKET = "KRW-BTC"
DEFAULT_LOOKBACK_DAYS = 90


# ── 인증 헬퍼 (exchange/crypto.py:86-102 패턴 그대로) ─────────

def _build_query_string(query: dict) -> str:
    """업비트 문서 기준 query hash 생성용 문자열 구성."""
    return unquote(urlencode(query, doseq=True))


def _auth_header(api_key: str, api_secret: str, query: Optional[dict] = None) -> dict:
    """JWT 인증 헤더 생성. query 파라미터가 있으면 SHA512 해시 포함."""
    payload = {
        "access_key": api_key,
        "nonce": str(uuid.uuid4()),
    }
    if query:
        query_string = _build_query_string(query).encode()
        m = hashlib.sha512()
        m.update(query_string)
        payload["query_hash"] = m.hexdigest()
        payload["query_hash_alg"] = "SHA512"

    token = jwt.encode(payload, api_secret, algorithm="HS512")
    return {"Authorization": f"Bearer {token}"}


# ── ISO 시각 → KST datetime ────────────────────────────────────

def to_kst(iso_str: str) -> datetime:
    """ISO 8601 문자열을 KST datetime 으로 변환한다."""
    return datetime.fromisoformat(iso_str).astimezone(KST)


# ── 이상치 수집 ────────────────────────────────────────────────

_anomaly_list: list[dict] = []


def warn_anomaly(uuid_val: str, executed_volume, executed_funds, reason: str) -> None:
    """이상치를 내부 목록에 기록한다."""
    _anomaly_list.append({
        "uuid": uuid_val,
        "executed_volume": executed_volume,
        "executed_funds": executed_funds,
        "reason": reason,
    })


# ── API 호출 ──────────────────────────────────────────────────

def _get(api_key: str, api_secret: str, path: str, params: dict) -> dict | list:
    """GET 요청 1회. 인증 헤더 포함."""
    headers = _auth_header(api_key, api_secret, params if params else None)
    resp = requests.get(BASE_URL + path, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_closed_orders(
    api_key: str,
    api_secret: str,
    market: str,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict]:
    """GET /v1/orders/closed 를 7일 윈도우로 분할 + 페이지네이션하여 전체 조회.

    states[]=cancel&states[]=done 둘 다 요청해 시장가 BUY 포함.
    """
    all_orders: list[dict] = []

    window_start = start_dt
    while window_start < end_dt:
        window_end = min(window_start + timedelta(days=WINDOW_DAYS), end_dt)

        # start_time, end_time: ISO 8601 (업비트는 +09:00 형식 지원)
        start_iso = window_start.isoformat(timespec="seconds")
        end_iso = window_end.isoformat(timespec="seconds")

        cursor_start = start_iso  # 페이지네이션 커서용
        last_count = -1

        while True:
            params = {
                "market": market,
                "states[]": ["cancel", "done"],
                "start_time": cursor_start,
                "end_time": end_iso,
                "limit": 100,
                "order_by": "asc",
            }
            data = _get(api_key, api_secret, "/v1/orders/closed", params)
            assert isinstance(data, list), f"closed orders 응답이 list가 아님: {type(data)}"

            if not data:
                break

            all_orders.extend(data)
            time.sleep(RATE_LIMIT_SLEEP_SEC)

            # 100건 미만이면 해당 윈도우 페이지 끝
            if len(data) < 100:
                break

            # 100건이면 마지막 created_at 으로 커서 이동
            # 업비트 start_time 의 inclusive/exclusive 가 doc 미명시이지만,
            # 같은 주문이 다음 페이지에 다시 와도 uuid dedup(seen) 으로 처리됨.
            # 동일 created_at 가 100건 이상인 케이스는 그리드 봇 운영에서
            # 사실상 발생하지 않지만(초당 100주문 미만) 무한루프 방지로 break.
            last_created_at = data[-1]["created_at"]
            if last_created_at == cursor_start:
                break
            cursor_start = last_created_at

        window_start = window_end

    # uuid 기준 중복 제거 (윈도우 경계 페이지네이션에서 겹칠 수 있음)
    seen: set[str] = set()
    deduped: list[dict] = []
    for o in all_orders:
        if o["uuid"] not in seen:
            seen.add(o["uuid"])
            deduped.append(o)

    return deduped


def fetch_order_detail(api_key: str, api_secret: str, order_uuid: str) -> dict:
    """GET /v1/order?uuid=... 1건 조회."""
    params = {"uuid": order_uuid}
    data = _get(api_key, api_secret, "/v1/order", params)
    assert isinstance(data, dict), f"order detail 응답이 dict가 아님: {type(data)}"
    return data


# ── 주문 시각 / 수치 처리 ──────────────────────────────────────

def _extract_time_key(
    order: dict, api_key: str, api_secret: str
) -> datetime:
    """주문의 time_key 결정.

    BUY(bid): created_at 기준 KST
    SELL(ask): trades 배열의 created_at 중 최댓값 KST
    """
    side = order["side"]
    if side == "bid":
        return to_kst(order["created_at"])
    elif side == "ask":
        detail = fetch_order_detail(api_key, api_secret, order["uuid"])
        time.sleep(RATE_LIMIT_SLEEP_SEC)
        trades = detail.get("trades") or []
        assert len(trades) > 0, f"trades 빈 배열: {order['uuid']}"
        order["_trade_count"] = len(trades)
        trade_times = [to_kst(t["created_at"]) for t in trades]
        return max(trade_times)
    else:
        # 알 수 없는 side는 created_at 사용
        return to_kst(order["created_at"])


def _to_decimal(val) -> Decimal:
    """None이면 assert, 아니면 Decimal(str(x)) 변환."""
    assert val is not None, f"None 값을 Decimal 변환 시도: {val!r}"
    return Decimal(str(val))


def _sell_trade_count(order: dict) -> int:
    """SELL 주문의 실제 trade fill 수. 테스트/과거 입력은 1건으로 간주한다."""
    raw_count = order.get("_trade_count")
    if raw_count is None:
        return 1
    count = int(raw_count)
    return count if count > 0 else 1


# ── 그룹키 ──────────────────────────────────────────────────────

def group_key(time_key: datetime, period: str) -> str:
    """period 별 그룹 키 문자열 반환."""
    if period == "daily":
        return time_key.strftime("%y-%m-%d")
    if period == "weekly":
        week_start = (time_key - timedelta(days=time_key.weekday())).date()
        week_end = week_start + timedelta(days=6)
        return f"{week_start:%y-%m-%d} ~ {week_end:%y-%m-%d}"
    if period == "monthly":
        return time_key.strftime("%y-%m")
    if period == "yearly":
        return time_key.strftime("%y")
    if period == "all":
        return "ALL"
    raise ValueError(f"알 수 없는 period: {period}")


# ── FIFO 매칭 엔진 ────────────────────────────────────────────

def run_fifo(
    sorted_orders: list[dict],
    reset_sell_uuids: set[str] | None = None,
) -> tuple[list[dict], list[dict], list[dict], list[dict], dict[int, list[dict]], list[dict]]:
    """슬롯 1:1 매칭 (글로벌 FIFO 가 아님).

    Math Expert APPROVED 산식. 슬롯별 큐로 분리하여 같은 슬롯의
    BUY ↔ SELL 만 매칭한다. identifier 패턴이 안 맞는 주문은 unparseable.

    의도된 동작: 글로벌 FIFO 와 다른 결과를 의도적으로 생산한다 (봇 슬롯 1:1 매핑 의미).

    Returns:
        realized_lines    : 매칭된 SELL 라인 목록
        unmatched_lines   : 같은 슬롯 BUY 큐 비어있어 매칭 못 한 SELL 라인 목록
        unparseable_buys  : identifier 패턴 안 맞는 BUY 주문 목록
        unparseable_sells : identifier 패턴 안 맞는 SELL 주문 목록
        queues_by_slot    : 슬롯별 잔여 BUY 큐 (매칭 후 남은 것)
        reset_residuals   : reset boundary 로 제거된 pre-reset 잔여 BUY 목록
    """
    reset_sell_uuids = reset_sell_uuids or set()
    queues_by_slot: dict[int, list[dict]] = {}
    realized_lines: list[dict] = []
    unmatched_lines: list[dict] = []
    unparseable_buys: list[dict] = []
    unparseable_sells: list[dict] = []
    reset_residuals: list[dict] = []

    for order in sorted_orders:
        exec_vol = _to_decimal(order["executed_volume"])
        exec_funds = _to_decimal(order["executed_funds"])
        paid_fee = _to_decimal(order["paid_fee"])
        time_key = order["_time_key"]
        is_reset_sell = is_reset_sell_order(order, reset_sell_uuids)
        slot = None if is_reset_sell else extract_slot_index(order.get("identifier"))

        if slot is None:
            if is_reset_sell:
                reset_sell_qty = exec_vol
                sell_gross_krw = exec_funds

                if sell_gross_krw == Decimal("0"):
                    if paid_fee == Decimal("0"):
                        warn_anomaly(
                            order["uuid"], exec_vol, exec_funds,
                            "reset sell_gross_krw=0 ∧ paid_fee=0 (체결 0건 의심)"
                        )
                        continue
                    else:
                        warn_anomaly(
                            order["uuid"], exec_vol, exec_funds,
                            "reset sell_gross_krw=0 이면서 paid_fee>0"
                        )
                        continue

                pre_reset_entries = sorted(
                    (
                        entry
                        for queue in queues_by_slot.values()
                        for entry in queue
                        if entry["qty"] > Decimal("0")
                    ),
                    key=lambda entry: (entry["time_key"], entry["buy_uuid"]),
                )
                remaining_qty = reset_sell_qty

                for head in pre_reset_entries:
                    if remaining_qty <= Decimal("0"):
                        break
                    take_qty = min(remaining_qty, head["qty"])
                    matched_cost = take_qty * head["unit_cost"]
                    ratio = take_qty / reset_sell_qty
                    matched_net_proceeds = sell_gross_krw * ratio - paid_fee * ratio
                    realized_pnl = matched_net_proceeds - matched_cost
                    realized_lines.append({
                        "time_key": time_key,
                        "realized_pnl": realized_pnl,
                        "matched_qty": take_qty,
                        "sell_uuid": order["uuid"],
                        "sell_trade_count": _sell_trade_count(order),
                        "slot": head["slot"],
                    })
                    head["qty"] -= take_qty
                    remaining_qty -= take_qty

                if remaining_qty > Decimal("0"):
                    ratio = remaining_qty / reset_sell_qty
                    unmatched_proceeds = sell_gross_krw * ratio - paid_fee * ratio
                    unmatched_lines.append({
                        "time_key": time_key,
                        "unmatched_proceeds": unmatched_proceeds,
                        "unmatched_qty": remaining_qty,
                        "sell_uuid": order["uuid"],
                        "slot": None,
                    })

                for head in pre_reset_entries:
                    if head["qty"] > Decimal("0"):
                        reset_residuals.append({
                            "time_key": time_key,
                            "slot": head["slot"],
                            "residual_qty": head["qty"],
                            "residual_cost": head["qty"] * head["unit_cost"],
                            "buy_uuid": head["buy_uuid"],
                        })

                for queue in queues_by_slot.values():
                    queue.clear()
                continue

            # identifier 패턴 안 맞음 (수동 주문, 외부 봇 등)
            entry = {
                "uuid": order["uuid"],
                "qty": exec_vol,
                "executed_funds": exec_funds,
                "time_key": time_key,
            }
            if order["side"] == "bid":
                unparseable_buys.append(entry)
            else:
                unparseable_sells.append(entry)
            continue

        if order["side"] == "bid":
            # ── BUY 처리: 슬롯 큐에 적재 ─────────────────────
            buy_qty = exec_vol                                   # Decimal BTC
            buy_total_cost = exec_funds + paid_fee               # Decimal KRW (수수료 포함)
            buy_unit_cost = buy_total_cost / buy_qty             # Decimal KRW/BTC
            queues_by_slot.setdefault(slot, []).append({
                "qty": buy_qty,
                "unit_cost": buy_unit_cost,
                "buy_uuid": order["uuid"],
                "time_key": time_key,
                "slot": slot,
            })

        elif order["side"] == "ask":
            # ── SELL 처리: 같은 슬롯 큐에서만 FIFO 매칭 ────────
            sell_qty = exec_vol
            sell_gross_krw = exec_funds

            # sell_gross_krw == 0 가드 (기존 동일)
            if sell_gross_krw == Decimal("0"):
                if paid_fee == Decimal("0"):
                    warn_anomaly(
                        order["uuid"], exec_vol, exec_funds,
                        "sell_gross_krw=0 ∧ paid_fee=0 (체결 0건 의심)"
                    )
                    continue
                else:
                    warn_anomaly(
                        order["uuid"], exec_vol, exec_funds,
                        "sell_gross_krw=0 이면서 paid_fee>0"
                    )
                    continue

            # 같은 슬롯의 큐에서만 FIFO 매칭
            queue = queues_by_slot.get(slot, [])
            remaining_qty = sell_qty
            matched_cost = Decimal("0")
            matched_qty_tot = Decimal("0")

            while remaining_qty > Decimal("0") and queue:
                head = queue[0]
                take_qty = min(remaining_qty, head["qty"])
                matched_cost += take_qty * head["unit_cost"]
                matched_qty_tot += take_qty
                head["qty"] -= take_qty
                remaining_qty -= take_qty
                if head["qty"] == Decimal("0"):
                    queue.pop(0)
                elif head["qty"] < Decimal("0"):
                    assert False, f"head.qty 음수: slot={slot} head={head}"

            # 수수료 안분 (수량비례 = ratio_matched)
            ratio_matched = matched_qty_tot / sell_qty
            matched_funds = sell_gross_krw * ratio_matched
            matched_fee = paid_fee * ratio_matched
            matched_sell_net = matched_funds - matched_fee
            realized_pnl = matched_sell_net - matched_cost

            if matched_qty_tot > Decimal("0"):
                realized_lines.append({
                    "time_key": time_key,
                    "realized_pnl": realized_pnl,
                    "matched_qty": matched_qty_tot,
                    "sell_uuid": order["uuid"],
                    "sell_trade_count": _sell_trade_count(order),
                    "slot": slot,
                })

            if remaining_qty > Decimal("0"):
                unmatched_qty = remaining_qty
                unmatched_funds = sell_gross_krw - matched_funds
                unmatched_fee = paid_fee - matched_fee
                unmatched_sell_net = unmatched_funds - unmatched_fee
                unmatched_lines.append({
                    "time_key": time_key,
                    "unmatched_proceeds": unmatched_sell_net,
                    "unmatched_qty": unmatched_qty,
                    "sell_uuid": order["uuid"],
                    "slot": slot,
                })

    return (
        realized_lines,
        unmatched_lines,
        unparseable_buys,
        unparseable_sells,
        queues_by_slot,
        reset_residuals,
    )


# ── 출력 ─────────────────────────────────────────────────────

def _fmt_krw(val: Decimal) -> str:
    """KRW 천단위 콤마 포맷."""
    # 소수점 반올림 후 정수 표시
    rounded = val.quantize(Decimal("1"))
    return f"{int(rounded):,}"


def _fmt_btc(val: Decimal) -> str:
    """BTC 8자리 소수 포맷."""
    return f"{val:.8f}"


def _print_realized_section(
    realized_lines: list[dict],
    periods: list[str],
    title: str = "[ 실현손익 ]",
) -> None:
    """period 별 realized 합계 섹션 출력."""
    print(title)
    header = (
        f"{'기간':<23} {'매도주문수':>9} {'체결건수':>8}"
        f" {'실현손익(KRW)':>18} {'매도수량(BTC)':>18}"
    )
    print(header)
    print("-" * len(header))

    for period in periods:
        # period 별 집계
        groups: dict[str, list[dict]] = defaultdict(list)
        for line in realized_lines:
            k = group_key(line["time_key"], period)
            groups[k].append(line)

        if not groups:
            print(
                f"{'(없음)':<23} {'0':>9} {'0':>8}"
                f" {'0':>18} {'0.00000000':>18}  [{period}]"
            )
            continue

        for k in sorted(groups.keys()):
            items = groups[k]
            total_pnl = sum((i["realized_pnl"] for i in items), Decimal("0"))
            total_qty = sum((i["matched_qty"] for i in items), Decimal("0"))
            sell_orders = {
                i["sell_uuid"]: int(i.get("sell_trade_count", 1))
                for i in items
            }
            order_count = len(sell_orders)
            trade_count = sum(sell_orders.values())
            print(
                f"{k:<23} {order_count:>9} {trade_count:>8}"
                f" {_fmt_krw(total_pnl):>18} {_fmt_btc(total_qty):>18}"
                f"  [{period}]"
            )


def _print_unmatched_section(
    unmatched_lines: list[dict],
    periods: list[str],
    title: str = "[ 미매칭(같은 슬롯 매수 큐 비어있음 — 윈도우 밖 또는 unparseable, PnL 아님) ]",
) -> None:
    """period 별 unmatched 섹션 출력."""
    print(title)
    header = f"{'기간':<23} {'건수':>8} {'매도순대금(KRW)':>18} {'매도수량(BTC)':>18}"
    print(header)
    print("-" * len(header))

    for period in periods:
        groups: dict[str, list[dict]] = defaultdict(list)
        for line in unmatched_lines:
            k = group_key(line["time_key"], period)
            groups[k].append(line)

        if not groups:
            print(f"{'(없음)':<23} {'0':>8} {'0':>18} {'0.00000000':>18}  [{period}]")
            continue

        for k in sorted(groups.keys()):
            items = groups[k]
            total_proceeds = sum((i["unmatched_proceeds"] for i in items), Decimal("0"))
            total_qty = sum((i["unmatched_qty"] for i in items), Decimal("0"))
            count = len(items)
            print(
                f"{k:<23} {count:>8} {_fmt_krw(total_proceeds):>18} {_fmt_btc(total_qty):>18}"
                f"  [{period}]"
            )


def _print_unparseable_section(
    unparseable_buys: list[dict],
    unparseable_sells: list[dict],
) -> None:
    """섹션 4: identifier 패턴 안 맞는 주문 출력."""
    print("[ 매칭 불가 주문 (identifier 패턴 안 맞음, 수동/외부 주문 의심) ]")
    if not unparseable_buys and not unparseable_sells:
        print("  (매칭 불가 주문 없음)")
        return

    print(f"  BUY {len(unparseable_buys)}건:")
    for entry in unparseable_buys:
        t = entry["time_key"].isoformat(timespec="seconds")
        print(
            f"    - uuid={entry['uuid']}"
            f" qty={_fmt_btc(entry['qty'])}"
            f" funds={_fmt_krw(entry['executed_funds'])} KRW"
            f" time={t}"
        )
    print(f"  SELL {len(unparseable_sells)}건:")
    for entry in unparseable_sells:
        t = entry["time_key"].isoformat(timespec="seconds")
        print(
            f"    - uuid={entry['uuid']}"
            f" qty={_fmt_btc(entry['qty'])}"
            f" funds={_fmt_krw(entry['executed_funds'])} KRW"
            f" time={t}"
        )


def _print_remaining_buy_section(queues_by_slot: dict[int, list[dict]]) -> None:
    """섹션 5: 슬롯별 잔여 BUY 큐 출력.

    가중평균 unit_cost: total_cost = Σ qty × unit_cost, avg = total_cost / total_qty
    슬롯 번호 오름차순 정렬.
    """
    print("[ 잔여 매수 (분석 윈도우 안 매수인데 매칭 SELL 없음 — 미실현 또는 매도 윈도우 밖) ]")

    # 잔여가 있는 슬롯만 필터
    remaining_slots = {
        slot: entries
        for slot, entries in queues_by_slot.items()
        if entries
    }

    if not remaining_slots:
        print("  (잔여 매수 없음)")
        return

    header = f"{'슬롯':>5} | {'잔여수량':>12} | {'평균 unit_cost':>16} | {'BUY 건수':>8}"
    print(header)
    print("-" * len(header))

    for slot in sorted(remaining_slots.keys()):
        entries = remaining_slots[slot]
        total_qty = sum((e["qty"] for e in entries), Decimal("0"))
        total_cost = sum((e["qty"] * e["unit_cost"] for e in entries), Decimal("0"))
        avg_unit_cost = total_cost / total_qty if total_qty > Decimal("0") else Decimal("0")
        count = len(entries)
        print(
            f"{slot:>5} | {_fmt_btc(total_qty):>12} | {_fmt_krw(avg_unit_cost):>16} | {count:>8}"
        )


def _print_reset_residual_section(reset_residuals: list[dict]) -> None:
    """reset boundary 로 future matching 에서 제외한 pre-reset 잔여 BUY 출력."""
    print("[ reset 잔여 조정 (pre-reset 매수 잔량, PnL 아님) ]")
    if not reset_residuals:
        print("  (reset 잔여 조정 없음)")
        return

    header = f"{'시각':<25} | {'슬롯':>5} | {'잔여수량':>12} | {'cost basis':>16} | {'BUY uuid':<36}"
    print(header)
    print("-" * len(header))
    for entry in reset_residuals:
        t = entry["time_key"].isoformat(timespec="seconds")
        print(
            f"{t:<25} | {entry['slot']:>5} | {_fmt_btc(entry['residual_qty']):>12} | "
            f"{_fmt_krw(entry['residual_cost']):>16} | {entry['buy_uuid']:<36}"
        )


def _print_anomaly_section() -> None:
    """이상치 경고 섹션 출력."""
    print("[ 이상치 경고 ]")
    if not _anomaly_list:
        print("  이상치 없음")
        return
    print(f"  총 {len(_anomaly_list)}건")
    for item in _anomaly_list:
        print(
            f"  uuid={item['uuid']}"
            f"  executed_volume={item['executed_volume']}"
            f"  executed_funds={item['executed_funds']}"
            f"  reason={item['reason']}"
        )


# ── argparse ─────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 scripts/upbit_realized_pnl.py",
        description="업비트 체결 주문 기반 실현손익 분석 (읽기 전용)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYY-MM-DD",
        help="조회 시작일 (기본: 오늘 기준 90일 전)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM-DD",
        help="조회 종료일 (기본: 오늘)",
    )
    parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly", "yearly", "all"],
        default="all",
        help="집계 단위 (기본: all — 5개 단위 모두 출력)",
    )
    parser.add_argument(
        "--market",
        default=DEFAULT_MARKET,
        help=f"업비트 마켓 코드 (기본: {DEFAULT_MARKET})",
    )
    parser.add_argument(
        "--reset-sell-uuid",
        action="append",
        default=[],
        help="과거 reset 전량 매도 주문 uuid (반복 지정 가능)",
    )
    return parser


# ── 메인 ─────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 날짜 범위 결정
    today_kst = datetime.now(KST).date()
    if args.to_date:
        to_date = date.fromisoformat(args.to_date)
    else:
        to_date = today_kst
    if args.from_date:
        from_date = date.fromisoformat(args.from_date)
    else:
        from_date = today_kst - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    if from_date > to_date:
        print(f"오류: --from ({from_date}) 이 --to ({to_date}) 보다 늦습니다.", file=sys.stderr)
        return 1

    # datetime (KST, 하루 시작/끝)
    start_dt = datetime(from_date.year, from_date.month, from_date.day,
                        0, 0, 0, tzinfo=KST)
    # 종료일 당일 자정(다음 날 0시)까지 포함
    end_dt = datetime(to_date.year, to_date.month, to_date.day,
                      23, 59, 59, tzinfo=KST)

    api_key = cfg.API_KEY
    api_secret = cfg.API_SECRET

    if not api_key or not api_secret:
        print("오류: API_KEY 또는 API_SECRET 이 설정되지 않았습니다.", file=sys.stderr)
        return 1

    if not cfg.STATE_BOT_KEY:
        print("오류: STATE_BOT_KEY 가 빈 문자열입니다. .env 또는 환경변수를 확인하세요.", file=sys.stderr)
        return 1

    market = args.market
    period_arg = args.period

    print(f"조회 범위: {from_date} ~ {to_date}  마켓: {market}")
    print("closed orders 수집 중...")

    # 1단계: closed orders 수집
    raw_orders = fetch_closed_orders(api_key, api_secret, market, start_dt, end_dt)
    print(f"  수집 완료: {len(raw_orders)}건 (cancel+done 포함)")

    # 2단계: 체결 0건 필터, 수치 검증, time_key 결정
    valid_orders: list[dict] = []
    for order in raw_orders:
        exec_vol = _to_decimal(order.get("executed_volume", "0"))

        # 체결 0건 skip (cancel/done 무관)
        if exec_vol == Decimal("0"):
            continue

        exec_funds = order.get("executed_funds")
        paid_fee = order.get("paid_fee")

        if exec_funds is None:
            warn_anomaly(order["uuid"], exec_vol, None, "executed_funds None")
            continue
        if paid_fee is None:
            warn_anomaly(order["uuid"], exec_vol, _to_decimal(exec_funds), "paid_fee None")
            continue

        exec_funds_d = _to_decimal(exec_funds)
        paid_fee_d = _to_decimal(paid_fee)

        # exec_funds == 0 ∧ exec_vol > 0 → 이상치 경고 후 skip
        if exec_funds_d == Decimal("0") and exec_vol > Decimal("0"):
            warn_anomaly(
                order["uuid"], exec_vol, exec_funds_d,
                "executed_funds=0 이면서 executed_volume>0"
            )
            continue

        # time_key 결정 (SELL의 경우 /v1/order 추가 호출)
        try:
            order["_time_key"] = _extract_time_key(order, api_key, api_secret)
        except AssertionError as e:
            warn_anomaly(order["uuid"], exec_vol, exec_funds_d, str(e))
            continue

        valid_orders.append(order)

    print(f"  유효 주문: {len(valid_orders)}건 (체결 0건, 이상치 제외 후)")

    # 3단계: time_key + uuid 기준 정렬
    sorted_orders = sorted(valid_orders, key=lambda o: (o["_time_key"], o["uuid"]))

    # 4단계: 슬롯별 매칭
    (
        realized_lines,
        unmatched_lines,
        unparseable_buys,
        unparseable_sells,
        queues_by_slot,
        reset_residuals,
    ) = run_fifo(sorted_orders, set(args.reset_sell_uuid))

    # 5단계: 출력
    # period=all 이면 5개 단위 모두 출력, 아니면 해당 단위만
    if period_arg == "all":
        periods_to_show = ["daily", "weekly", "monthly", "yearly", "all"]
    else:
        periods_to_show = [period_arg]

    print()
    print("=" * 80)
    _print_realized_section(realized_lines, periods_to_show)
    print()
    _print_unmatched_section(unmatched_lines, periods_to_show)
    print()
    _print_unparseable_section(unparseable_buys, unparseable_sells)
    print()
    _print_remaining_buy_section(queues_by_slot)
    print()
    _print_reset_residual_section(reset_residuals)
    print()
    _print_anomaly_section()
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
