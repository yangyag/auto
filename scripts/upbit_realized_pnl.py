#!/usr/bin/env python3
"""업비트 실현 손익 분석 (설정 SYMBOL 기본, read-only).

매칭 방식: 슬롯 1:1 매칭. identifier 의 슬롯 번호로 BUY ↔ SELL 짝지음.
글로벌 FIFO 와 의도적으로 다른 결과를 생산 (봇 슬롯 단위 매핑 의미).

identifier 형식: '{STATE_BOT_KEY}-{buy|sell}-{slot}-{ms}-{hex12}'
발급 지점: main.py:ensure_order_identifier() (line 110-118).
STATE_BOT_KEY 는 cfg.STATE_BOT_KEY 로 동적 참조 (운영 환경별 호환).

한계: 같은 millisecond 의 BUY/SELL trade 가 슬롯 안에서 동률일 때 uuid
tie-break 로 SELL 이 먼저 처리될 가능성 (운영상 거의 불가능, 안내 노트).

사용법:
    .venv/bin/python scripts/upbit_realized_pnl.py [--period d|w|m|y]
        [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--market MARKET]
        [--reset-sell-uuid UUID] [--lookback DAYS]

기본값:
    옵션 없음 : 오늘 기준 최근 90일, daily/weekly/monthly/yearly/ALL 5개 섹션 출력
    --period  : d=오늘, w=이번주, m=이번달, y=이번년
    --from/to : 사용자가 직접 지정한 기간 1개 합산 출력
    --market   : app.config.settings.SYMBOL
    --lookback : 30일 (default: DEFAULT_LOOKBACK_DAYS = 30)

--lookback 파라미터:
    조회 시작일 이전으로 추가 조회할 기간(일). 실현손익 매칭 과정에서
    표시 기간 전의 과거 BUY 주문들과 reset 직전 취소된 TP SELL 주문들을
    포함하기 위해 사용한다.

    3개 윈도우:
    1. fetch 윈도우: 표시 시작일 - lookback ~ 표시 종료일 (API 조회 범위, 모든 BUY 포함)
    2. 사용자 입력: --period 또는 --from/--to 로 정한 논리 범위
    3. 표시 윈도우: 출력에 표시되는 범위, 이 범위의 SELL만 보임

    fetch 범위 경계 근처(표시 시작일 이후 1일)에서 BUY가 조회되면 경고를 출력한다.
    이는 lookback이 부족하여 더 오래된 BUY를 누락했을 가능성을 의미한다.
    경고가 발생하면 --lookback을 추천값 이상으로 증가시켜 재실행하면 된다.

    예:
    - 오늘 손익만 분석: --period d
    - 이번주 손익만 분석: --period w
    - 5월 1일~31일 손익 + 4월 중 BUY: --from 2026-05-01 --to 2026-05-31 --lookback 30
    - 4월 중 의심 주문 정산 시 lookback 60일로 안전 마진 추가:
      --from 2026-04-01 --to 2026-04-30 --lookback 60
"""
import argparse
import hashlib
import re
import sys
import time
import uuid
import warnings
from collections import defaultdict
from dataclasses import dataclass
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
DEFAULT_MARKET = cfg.SYMBOL
DEFAULT_REPORT_DAYS = 90
DEFAULT_LOOKBACK_DAYS = 30
RESET_QTY_TOLERANCE = Decimal("0.00000001")
DEFAULT_PERIODS_TO_SHOW = ["daily", "weekly", "monthly", "yearly", "all"]
PERIOD_PRESET_TO_GROUP = {
    "d": "daily",
    "w": "weekly",
    "m": "monthly",
    "y": "yearly",
}
PERIOD_PRESET_LABELS = {
    "d": "오늘",
    "w": "이번주",
    "m": "이번달",
    "y": "이번년",
}
PERIOD_PRESET_ALIASES = {
    "d": "d",
    "day": "d",
    "daily": "d",
    "today": "d",
    "w": "w",
    "week": "w",
    "weekly": "w",
    "m": "m",
    "month": "m",
    "monthly": "m",
    "y": "y",
    "year": "y",
    "yearly": "y",
}


def default_market() -> str:
    return cfg.SYMBOL


def market_base_currency(market: str) -> str:
    if "-" not in market:
        return market.upper()
    return market.split("-", 1)[1].upper()


@dataclass(frozen=True)
class ReportWindow:
    from_date: date
    to_date: date
    periods_to_show: list[str]
    mode_label: str


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


def _to_decimal_or_zero(val) -> Decimal:
    if val in (None, ""):
        return Decimal("0")
    return Decimal(str(val))


def _cancelled_tp_sell_qty(order: dict) -> Decimal:
    return _to_decimal_or_zero(order.get("remaining_volume") or order.get("volume"))


def is_cancelled_tp_sell_candidate(order: dict) -> bool:
    """reset 직전 취소된 봇 TP SELL 주문 후보인지 판정한다.

    Upbit closed orders에는 취소 시각이 없고 생성 시각만 있으므로, reset
    매도 시점에는 최근 취소된 봇 SELL 후보들을 수량으로 맞춰 사용한다.
    """
    if order.get("side") != "ask":
        return False
    if order.get("state") != "cancel":
        return False
    if _to_decimal_or_zero(order.get("executed_volume")) != Decimal("0"):
        return False
    if extract_slot_index(order.get("identifier")) is None:
        return False
    return _cancelled_tp_sell_qty(order) > Decimal("0")


def _sell_trade_count(order: dict) -> int:
    """SELL 주문의 실제 trade fill 수. 테스트/과거 입력은 1건으로 간주한다."""
    raw_count = order.get("_trade_count")
    if raw_count is None:
        return 1
    count = int(raw_count)
    return count if count > 0 else 1


def _select_reset_cancelled_sell_targets(
    cancelled_sell_candidates: list[dict],
    reset_sell_qty: Decimal,
) -> list[dict]:
    """최근 취소된 TP SELL 후보들 중 reset 수량에 해당하는 슬롯 목표를 고른다."""
    if reset_sell_qty <= Decimal("0"):
        return []

    selected: list[dict] = []
    selected_qty = Decimal("0")
    for candidate in sorted(
        cancelled_sell_candidates,
        key=lambda item: (item["time_key"], item["uuid"]),
        reverse=True,
    ):
        if selected_qty >= reset_sell_qty - RESET_QTY_TOLERANCE:
            break
        remaining_needed = reset_sell_qty - selected_qty
        take_qty = min(candidate["qty"], remaining_needed)
        if take_qty <= Decimal("0"):
            continue
        selected.append({**candidate, "qty": take_qty})
        selected_qty += take_qty

    if selected_qty < reset_sell_qty - RESET_QTY_TOLERANCE:
        return []

    return sorted(selected, key=lambda item: (item["slot"], item["time_key"], item["uuid"]))


def _record_reset_residuals(
    queues_by_slot: dict[int, list[dict]],
    reset_time_key: datetime,
) -> list[dict]:
    residuals: list[dict] = []
    for queue in queues_by_slot.values():
        for head in queue:
            if head["qty"] > Decimal("0"):
                residuals.append({
                    "time_key": reset_time_key,
                    "slot": head["slot"],
                    "residual_qty": head["qty"],
                    "residual_cost": head["qty"] * head["unit_cost"],
                    "buy_uuid": head["buy_uuid"],
                })
    return residuals


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
    if period == "range":
        return "조회범위"
    raise ValueError(f"알 수 없는 period: {period}")


def parse_period_preset(value: str) -> str:
    """CLI --period 값을 d/w/m/y 프리셋으로 정규화한다."""
    normalized = PERIOD_PRESET_ALIASES.get(value.lower())
    if normalized is None:
        valid = ", ".join(PERIOD_PRESET_TO_GROUP.keys())
        raise argparse.ArgumentTypeError(f"--period 는 {valid} 중 하나여야 합니다")
    return normalized


def resolve_report_window(args: argparse.Namespace, today_kst: date) -> ReportWindow:
    """CLI 옵션을 표시 범위와 출력 집계 단위로 변환한다.

    - 옵션 없음: 기존 운영 기본값처럼 최근 90일 전체 섹션 출력
    - --period d/w/m/y: 오늘/이번주/이번달/이번년 프리셋
    - --from/--to: 사용자가 지정한 기간 하나를 합산 출력
    """
    has_custom_range = bool(args.from_date or args.to_date)
    if args.period and has_custom_range:
        raise ValueError("--period 와 --from/--to 는 같이 사용할 수 없습니다")

    if has_custom_range:
        if not args.from_date:
            raise ValueError("--to 만 단독으로 사용할 수 없습니다. --from YYYY-MM-DD 를 함께 지정하세요")
        from_date = date.fromisoformat(args.from_date)
        to_date = date.fromisoformat(args.to_date) if args.to_date else today_kst
        if from_date > to_date:
            raise ValueError(f"--from ({from_date}) 이 --to ({to_date}) 보다 늦습니다")
        return ReportWindow(
            from_date=from_date,
            to_date=to_date,
            periods_to_show=["range"],
            mode_label="직접지정",
        )

    if args.period:
        if args.period == "d":
            from_date = today_kst
        elif args.period == "w":
            from_date = today_kst - timedelta(days=today_kst.weekday())
        elif args.period == "m":
            from_date = date(today_kst.year, today_kst.month, 1)
        elif args.period == "y":
            from_date = date(today_kst.year, 1, 1)
        else:
            raise ValueError(f"알 수 없는 --period 값: {args.period}")
        return ReportWindow(
            from_date=from_date,
            to_date=today_kst,
            periods_to_show=[PERIOD_PRESET_TO_GROUP[args.period]],
            mode_label=PERIOD_PRESET_LABELS[args.period],
        )

    return ReportWindow(
        from_date=today_kst - timedelta(days=DEFAULT_REPORT_DAYS),
        to_date=today_kst,
        periods_to_show=DEFAULT_PERIODS_TO_SHOW,
        mode_label="전체",
    )


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
    cancelled_sell_candidates: list[dict] = []

    for order in sorted_orders:
        exec_vol = _to_decimal(order["executed_volume"])
        exec_funds = _to_decimal(order["executed_funds"])
        paid_fee = _to_decimal(order["paid_fee"])
        time_key = order["_time_key"]
        is_reset_sell = is_reset_sell_order(order, reset_sell_uuids)
        slot = None if is_reset_sell else extract_slot_index(order.get("identifier"))

        if order.get("_cancelled_tp_sell_candidate"):
            if slot is not None:
                cancelled_sell_candidates.append({
                    "slot": slot,
                    "qty": _cancelled_tp_sell_qty(order),
                    "time_key": time_key,
                    "uuid": order["uuid"],
                })
            continue

        reset_targets: list[dict] = []
        if slot is None and order.get("side") == "ask" and exec_vol > Decimal("0"):
            reset_targets = _select_reset_cancelled_sell_targets(
                cancelled_sell_candidates,
                exec_vol,
            )
            if reset_targets:
                is_reset_sell = True

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

                remaining_qty = reset_sell_qty

                if reset_targets:
                    for target in reset_targets:
                        remaining_qty -= target["qty"]
                        target_remaining = target["qty"]
                        target_matched_cost = Decimal("0")
                        target_matched_qty = Decimal("0")
                        queue = queues_by_slot.get(target["slot"], [])

                        while target_remaining > Decimal("0") and queue:
                            head = queue[0]
                            take_qty = min(target_remaining, head["qty"])
                            target_matched_cost += take_qty * head["unit_cost"]
                            target_matched_qty += take_qty
                            head["qty"] -= take_qty
                            target_remaining -= take_qty
                            if head["qty"] == Decimal("0"):
                                queue.pop(0)
                            elif head["qty"] < Decimal("0"):
                                assert False, f"head.qty 음수: slot={target['slot']} head={head}"

                        if target_matched_qty > Decimal("0"):
                            ratio = target_matched_qty / reset_sell_qty
                            matched_net_proceeds = sell_gross_krw * ratio - paid_fee * ratio
                            realized_pnl = matched_net_proceeds - target_matched_cost
                            realized_lines.append({
                                "time_key": time_key,
                                "realized_pnl": realized_pnl,
                                "matched_qty": target_matched_qty,
                                "sell_uuid": order["uuid"],
                                "sell_trade_count": _sell_trade_count(order),
                                "slot": target["slot"],
                            })

                        if target_remaining > RESET_QTY_TOLERANCE:
                            ratio = target_remaining / reset_sell_qty
                            unmatched_proceeds = sell_gross_krw * ratio - paid_fee * ratio
                            unmatched_lines.append({
                                "time_key": time_key,
                                "unmatched_proceeds": unmatched_proceeds,
                                "unmatched_qty": target_remaining,
                                "sell_uuid": order["uuid"],
                                "slot": target["slot"],
                            })
                else:
                    pre_reset_entries = sorted(
                        (
                            entry
                            for queue in queues_by_slot.values()
                            for entry in queue
                            if entry["qty"] > Decimal("0")
                        ),
                        key=lambda entry: (entry["time_key"], entry["buy_uuid"]),
                    )

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

                if remaining_qty > RESET_QTY_TOLERANCE:
                    ratio = remaining_qty / reset_sell_qty
                    unmatched_proceeds = sell_gross_krw * ratio - paid_fee * ratio
                    unmatched_lines.append({
                        "time_key": time_key,
                        "unmatched_proceeds": unmatched_proceeds,
                        "unmatched_qty": remaining_qty,
                        "sell_uuid": order["uuid"],
                        "slot": None,
                    })

                reset_residuals.extend(_record_reset_residuals(queues_by_slot, time_key))

                for queue in queues_by_slot.values():
                    queue.clear()
                cancelled_sell_candidates.clear()
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
            buy_qty = exec_vol                                   # Decimal base asset
            buy_total_cost = exec_funds + paid_fee               # Decimal KRW (수수료 포함)
            buy_unit_cost = buy_total_cost / buy_qty             # Decimal KRW/base asset
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


def _fmt_asset_qty(val: Decimal) -> str:
    """기초자산 수량 8자리 소수 포맷."""
    return f"{val:.8f}"


def _fmt_btc(val: Decimal) -> str:
    return _fmt_asset_qty(val)


def _print_realized_section(
    realized_lines: list[dict],
    periods: list[str],
    title: str = "[ 실현손익 ]",
    base_currency: str = "BTC",
) -> None:
    """period 별 realized 합계 섹션 출력."""
    print(title)
    header = (
        f"{'기간':<23} {'매도주문수':>9} {'체결건수':>8}"
        f" {'실현손익(KRW)':>18} {f'매도수량({base_currency})':>18}"
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
    base_currency: str = "BTC",
) -> None:
    """period 별 unmatched 섹션 출력."""
    print(title)
    header = f"{'기간':<23} {'건수':>8} {'매도순대금(KRW)':>18} {f'매도수량({base_currency})':>18}"
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
    display_start_dt: datetime,
    display_end_dt: datetime,
) -> None:
    """섹션 4: identifier 패턴 안 맞는 주문 출력 (display 윈도우 필터 적용)."""
    # display 윈도우 안의 unparseable만 출력
    filtered_buys = [
        e for e in unparseable_buys
        if display_start_dt <= e["time_key"] <= display_end_dt
    ]
    filtered_sells = [
        e for e in unparseable_sells
        if display_start_dt <= e["time_key"] <= display_end_dt
    ]

    print("[ 매칭 불가 주문 (identifier 패턴 안 맞음, 수동/외부 주문 의심) ]")
    if not filtered_buys and not filtered_sells:
        print("  (매칭 불가 주문 없음)")
        return

    print(f"  BUY {len(filtered_buys)}건:")
    for entry in filtered_buys:
        t = entry["time_key"].isoformat(timespec="seconds")
        print(
            f"    - uuid={entry['uuid']}"
            f" qty={_fmt_btc(entry['qty'])}"
            f" funds={_fmt_krw(entry['executed_funds'])} KRW"
            f" time={t}"
        )
    print(f"  SELL {len(filtered_sells)}건:")
    for entry in filtered_sells:
        t = entry["time_key"].isoformat(timespec="seconds")
        print(
            f"    - uuid={entry['uuid']}"
            f" qty={_fmt_btc(entry['qty'])}"
            f" funds={_fmt_krw(entry['executed_funds'])} KRW"
            f" time={t}"
        )


def _print_outside_display_window_section(outside_sell_orders: list[dict]) -> None:
    """디스플레이 윈도우 외부 SELL 주문 (읽기 전용 정보, PnL 아님)."""
    print("[ 디스플레이 윈도우 외부 주문 (lookback으로 수집했으나 표시 범위 밖, read-only) ]")
    if not outside_sell_orders:
        print("  (윈도우 외부 주문 없음)")
        return

    print(f"  SELL {len(outside_sell_orders)}건 (과거 BUY 매칭에만 사용):")
    for order in outside_sell_orders:
        t = order["_time_key"].isoformat(timespec="seconds")
        exec_vol = _to_decimal(order["executed_volume"])
        exec_funds = _to_decimal(order["executed_funds"])
        print(
            f"    - uuid={order['uuid']}"
            f" qty={_fmt_btc(exec_vol)}"
            f" funds={_fmt_krw(exec_funds)} KRW"
            f" time={t} (created_at: {order['created_at']})"
        )


def _print_fetch_boundary_warning_section(
    sorted_orders: list[dict],
    fetch_start_dt: datetime,
    lookback_days: int,
) -> None:
    """fetch 범위 경계 근처에서 소비된 BUY 경고 (슬롯 FIFO 특성상 mis-match 위험)."""
    boundary_margin_dt = fetch_start_dt + timedelta(days=1)

    # sorted_orders에서 fetch_start ~ +1일 사이에 생성된 BUY를 찾음
    near_boundary_buys = [
        o for o in sorted_orders
        if o["side"] == "bid" and fetch_start_dt <= o["_time_key"] < boundary_margin_dt
    ]

    if not near_boundary_buys:
        return

    print(
        "[ 경고: fetch 범위 경계 근처 BUY 감지 (lookback 부족 위험) ]"
    )
    print(
        f"  lookback={lookback_days}일로 fetch_start({fetch_start_dt.strftime('%Y-%m-%d')}) "
        f"에서 {len(near_boundary_buys)}건의 BUY가 조회됨."
    )
    print(
        "  → 이 BUY들이 SELL과 매칭되면, 경계 밖의 더 오래된 BUY 누락으로 인해"
    )
    print(
        "     현재 SELL이 잘못된 BUY와 매칭되어 PnL이 부정확할 수 있습니다."
    )
    print(
        f"  → 정확한 실현손익을 원하면 --lookback을 {lookback_days + 15}일 이상으로 증가시켜 재실행하세요."
    )
    print()


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


def print_report_sections(
    *,
    realized_lines: list[dict],
    unmatched_lines: list[dict],
    unparseable_buys: list[dict],
    unparseable_sells: list[dict],
    outside_sell_orders: list[dict],
    queues_by_slot: dict[int, list[dict]],
    reset_residuals: list[dict],
    sorted_orders: list[dict],
    display_start_dt: datetime,
    display_end_dt: datetime,
    fetch_start_dt: datetime,
    lookback_days: int,
    periods: list[str],
    market: str,
) -> None:
    base_currency = market_base_currency(market)

    print()
    print("=" * 80)
    _print_realized_section(realized_lines, periods, base_currency=base_currency)
    print()
    _print_unmatched_section(unmatched_lines, periods, base_currency=base_currency)
    print()
    _print_unparseable_section(unparseable_buys, unparseable_sells, display_start_dt, display_end_dt)
    print()
    _print_outside_display_window_section(outside_sell_orders)
    print()
    _print_fetch_boundary_warning_section(sorted_orders, fetch_start_dt, lookback_days)
    print()
    _print_remaining_buy_section(queues_by_slot)
    print()
    _print_reset_residual_section(reset_residuals)
    print()
    _print_anomaly_section()
    print("=" * 80)


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
        help="직접 조회 시작일 (--period 와 같이 사용 불가)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM-DD",
        help="직접 조회 종료일 (기본: 오늘, --period 와 같이 사용 불가)",
    )
    parser.add_argument(
        "--period",
        type=parse_period_preset,
        metavar="{d,w,m,y}",
        help="기간 프리셋: d=오늘, w=이번주, m=이번달, y=이번년 (옵션 없으면 최근 90일 전체)",
    )
    parser.add_argument(
        "--market",
        default=default_market(),
        help=f"업비트 마켓 코드 (기본: {default_market()})",
    )
    parser.add_argument(
        "--reset-sell-uuid",
        action="append",
        default=[],
        help="과거 reset 전량 매도 주문 uuid (반복 지정 가능)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        metavar="DAYS",
        help=f"표시 시작일 이전 매칭용 closed orders 추가 조회 기간, 단위: 일 (기본: {DEFAULT_LOOKBACK_DAYS})",
    )
    return parser


# ── 메인 ─────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 날짜 범위 결정
    today_kst = datetime.now(KST).date()
    try:
        report_window = resolve_report_window(args, today_kst)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    user_from_date = report_window.from_date
    user_to_date = report_window.to_date

    # fetch 범위: lookback margin 포함
    fetch_from_date = user_from_date - timedelta(days=args.lookback)

    # datetime (KST, 하루 시작/끝)
    fetch_start_dt = datetime(fetch_from_date.year, fetch_from_date.month, fetch_from_date.day,
                              0, 0, 0, tzinfo=KST)
    # 종료일 당일 자정(다음 날 0시)까지 포함
    display_end_dt = datetime(user_to_date.year, user_to_date.month, user_to_date.day,
                              23, 59, 59, tzinfo=KST)

    # 표시용 윈도우
    display_start_dt = datetime(user_from_date.year, user_from_date.month, user_from_date.day,
                                0, 0, 0, tzinfo=KST)

    api_key = cfg.API_KEY
    api_secret = cfg.API_SECRET

    if not api_key or not api_secret:
        print("오류: API_KEY 또는 API_SECRET 이 설정되지 않았습니다.", file=sys.stderr)
        return 1

    if not cfg.STATE_BOT_KEY:
        print("오류: STATE_BOT_KEY 가 빈 문자열입니다. .env 또는 환경변수를 확인하세요.", file=sys.stderr)
        return 1

    market = args.market

    print(f"조회 범위: {user_from_date} ~ {user_to_date}  마켓: {market}  모드: {report_window.mode_label}")
    if args.lookback > 0:
        print(f"매칭용 lookback: {args.lookback}일 (fetch: {fetch_from_date} ~ {user_to_date})")
    print("closed orders 수집 중...")

    # 1단계: closed orders 수집 (fetch 범위로 확장해서 과거 BUY 포함)
    raw_orders = fetch_closed_orders(api_key, api_secret, market, fetch_start_dt, display_end_dt)
    print(f"  수집 완료: {len(raw_orders)}건 (cancel+done 포함)")

    # 2단계: 체결 0건 필터, 수치 검증, time_key 결정
    valid_orders: list[dict] = []
    for order in raw_orders:
        exec_vol = _to_decimal(order.get("executed_volume", "0"))

        # 체결 0건 cancel SELL은 reset 매칭용 후보로 보존한다.
        if exec_vol == Decimal("0"):
            if is_cancelled_tp_sell_candidate(order):
                order["executed_funds"] = order.get("executed_funds") or "0"
                order["paid_fee"] = order.get("paid_fee") or "0"
                order["_time_key"] = to_kst(order["created_at"])
                order["_cancelled_tp_sell_candidate"] = True
                valid_orders.append(order)
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

    valid_trade_count = sum(
        1 for order in valid_orders
        if not order.get("_cancelled_tp_sell_candidate")
    )
    reset_candidate_count = len(valid_orders) - valid_trade_count
    print(
        f"  유효 주문: {valid_trade_count}건 "
        f"(reset 매칭 후보 {reset_candidate_count}건 별도 보존)"
    )

    # 3단계: time_key + uuid 기준 정렬
    sorted_orders = sorted(valid_orders, key=lambda o: (o["_time_key"], o["uuid"]))

    # 4단계: 슬롯별 매칭 (확장 fetch 전체 사용)
    (
        realized_lines,
        unmatched_lines,
        unparseable_buys,
        unparseable_sells,
        queues_by_slot,
        reset_residuals,
    ) = run_fifo(sorted_orders, set(args.reset_sell_uuid))

    # 5단계: 표시용 윈도우 필터링 (SELL의 _time_key가 display 범위 내인 것만)
    display_realized_lines = [
        x for x in realized_lines
        if display_start_dt <= x["time_key"] <= display_end_dt
    ]
    display_unmatched_lines = [
        x for x in unmatched_lines
        if display_start_dt <= x["time_key"] <= display_end_dt
    ]
    # 윈도우 밖 SELL 주문 수집 (read-only 정보)
    outside_sell_orders = [
        o for o in sorted_orders
        if (
            o["side"] == "ask"
            and not o.get("_cancelled_tp_sell_candidate")
            and _to_decimal(o["executed_volume"]) > Decimal("0")
            and not (display_start_dt <= o["_time_key"] <= display_end_dt)
        )
    ]

    # 6단계: 출력
    periods_to_show = report_window.periods_to_show
    print_report_sections(
        realized_lines=display_realized_lines,
        unmatched_lines=display_unmatched_lines,
        unparseable_buys=unparseable_buys,
        unparseable_sells=unparseable_sells,
        outside_sell_orders=outside_sell_orders,
        queues_by_slot=queues_by_slot,
        reset_residuals=reset_residuals,
        sorted_orders=sorted_orders,
        display_start_dt=display_start_dt,
        display_end_dt=display_end_dt,
        fetch_start_dt=fetch_start_dt,
        lookback_days=args.lookback,
        periods=periods_to_show,
        market=market,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
