"""외부 알림 (Slack, Telegram 등) 전송"""
import logging
from decimal import Decimal
from enum import Enum
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class StopLossEventKind(Enum):
    """손절 이벤트 종류"""
    ARMED = "armed"  # 손절 발동 준비 (캔들 조건 만족)
    EXECUTED = "executed"  # 손절 실행 완료 (청산 완료)
    FAILED = "failed"  # 손절 실행 실패


def send_stop_loss_notification(
    webhook_url: Optional[str],
    kind: StopLossEventKind,
    level: int,
    current_price: Decimal,
    threshold: Decimal,
    lower_price: Decimal,
    symbol: str = "KRW-BTC",
    liquidated_qty: Optional[Decimal] = None,
    failed_slots: Optional[list[int]] = None,
) -> bool:
    """
    손절 이벤트 알림 전송 (Webhook).

    Args:
        webhook_url: 외부 알림 Webhook URL (e.g. Slack Incoming Webhook)
        kind: 이벤트 종류 (ARMED/EXECUTED/FAILED)
        level: 손절 단계 (0=L0, 1=L1, 2=L2)
        current_price: 현재가
        threshold: 손절 임계값
        lower_price: 그리드 최하단 가격
        symbol: 종목 심볼
        liquidated_qty: 청산 수량 (EXECUTED 시)
        failed_slots: 실패 슬롯 목록 (FAILED 시)

    Returns:
        bool: 전송 성공 여부 (실패해도 로그만 남기고 True 반환)
    """
    if not webhook_url:
        logger.debug("[STOP_LOSS_NOTIFIER] Webhook URL 미설정. 알림 전송 스킵.")
        return True

    if not requests:
        logger.warning("[STOP_LOSS_NOTIFIER] requests 모듈 미설치. 알림 전송 불가.")
        return True

    try:
        payload = _build_webhook_payload(
            kind=kind,
            level=level,
            current_price=current_price,
            threshold=threshold,
            lower_price=lower_price,
            symbol=symbol,
            liquidated_qty=liquidated_qty,
            failed_slots=failed_slots,
        )

        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"[STOP_LOSS_NOTIFIER] {kind.value} 알림 전송 성공")
        return True
    except Exception as e:
        logger.warning(f"[STOP_LOSS_NOTIFIER] 알림 전송 실패: {e}")
        return True


def _build_webhook_payload(
    kind: StopLossEventKind,
    level: int,
    current_price: Decimal,
    threshold: Decimal,
    lower_price: Decimal,
    symbol: str,
    liquidated_qty: Optional[Decimal],
    failed_slots: Optional[list[int]],
) -> dict:
    """Webhook 페이로드 구성 (Slack 형식)"""
    level_name = f"L{level}"
    pct_drop = ((lower_price - current_price) / lower_price * 100) if lower_price > 0 else 0

    if kind == StopLossEventKind.ARMED:
        title = f"🚨 손절 {level_name} 발동 준비"
        color = "#FFA500"  # 주황색
        text = f"""
심볼: {symbol}
현재가: {current_price}
임계값: {threshold}
하락률: {pct_drop:.2f}% (기준: {lower_price})
상태: 손절 {level_name} 조건 만족. 청산 준비 중.
        """.strip()
    elif kind == StopLossEventKind.EXECUTED:
        title = f"✅ 손절 {level_name} 청산 완료"
        color = "#36A64F"  # 초록색
        text = f"""
심볼: {symbol}
현재가: {current_price}
임계값: {threshold}
청산수량: {liquidated_qty} BTC
상태: 손절 {level_name} 청산 완료.
        """.strip()
    else:  # FAILED
        title = f"⚠️ 손절 {level_name} 실행 실패"
        color = "#FF0000"  # 빨강색
        text = f"""
심볼: {symbol}
현재가: {current_price}
임계값: {threshold}
실패 슬롯: {failed_slots}
상태: 일부 슬롯의 청산에 실패했습니다.
        """.strip()

    return {
        "attachments": [
            {
                "fallback": title,
                "color": color,
                "title": title,
                "text": text,
                "mrkdwn_in": ["text"],
            }
        ]
    }
