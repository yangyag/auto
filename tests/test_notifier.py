"""외부 알림 (Webhook) 전송 테스트"""
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.utils.notifier import (
    send_stop_loss_notification,
    StopLossEventKind,
    _build_webhook_payload,
)


class TestStopLossNotifier(unittest.TestCase):
    """손절 이벤트 알림 테스트"""

    def test_send_stop_loss_notification_armed_event(self):
        """ARMED 이벤트: 손절 발동 준비"""
        with patch("app.utils.notifier.requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_requests.post.return_value = mock_response

            result = send_stop_loss_notification(
                webhook_url="https://hooks.slack.com/services/test",
                kind=StopLossEventKind.ARMED,
                level=1,
                current_price=Decimal("75000000"),
                threshold=Decimal("80000000"),
                lower_price=Decimal("100000000"),
                symbol="KRW-BTC",
            )

            self.assertTrue(result)
            mock_requests.post.assert_called_once()
            call_args = mock_requests.post.call_args
            self.assertIn("hooks.slack.com", call_args[0][0])
            payload = call_args[1]["json"]
            self.assertIn("attachments", payload)

    def test_send_stop_loss_notification_executed_event(self):
        """EXECUTED 이벤트: 청산 완료"""
        with patch("app.utils.notifier.requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_requests.post.return_value = mock_response

            result = send_stop_loss_notification(
                webhook_url="https://hooks.slack.com/services/test",
                kind=StopLossEventKind.EXECUTED,
                level=2,
                current_price=Decimal("65000000"),
                threshold=Decimal("70000000"),
                lower_price=Decimal("100000000"),
                symbol="KRW-BTC",
                liquidated_qty=Decimal("0.005"),
            )

            self.assertTrue(result)
            mock_requests.post.assert_called_once()

    def test_send_stop_loss_notification_failed_event(self):
        """FAILED 이벤트: 청산 실패"""
        with patch("app.utils.notifier.requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_requests.post.return_value = mock_response

            result = send_stop_loss_notification(
                webhook_url="https://hooks.slack.com/services/test",
                kind=StopLossEventKind.FAILED,
                level=1,
                current_price=Decimal("75000000"),
                threshold=Decimal("80000000"),
                lower_price=Decimal("100000000"),
                symbol="KRW-BTC",
                failed_slots=[0, 2, 4],
            )

            self.assertTrue(result)
            mock_requests.post.assert_called_once()

    def test_send_stop_loss_notification_no_webhook_url(self):
        """Webhook URL 없음: 로그만 기록하고 True 반환"""
        result = send_stop_loss_notification(
            webhook_url=None,
            kind=StopLossEventKind.ARMED,
            level=1,
            current_price=Decimal("75000000"),
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            symbol="KRW-BTC",
        )

        self.assertTrue(result)

    def test_send_stop_loss_notification_empty_webhook_url(self):
        """Webhook URL 빈 문자열: 로그만 기록하고 True 반환"""
        result = send_stop_loss_notification(
            webhook_url="",
            kind=StopLossEventKind.ARMED,
            level=1,
            current_price=Decimal("75000000"),
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            symbol="KRW-BTC",
        )

        self.assertTrue(result)

    def test_send_stop_loss_notification_requests_exception(self):
        """요청 실패: 예외 로그하고 True 반환 (손절 흐름 진행)"""
        with patch("app.utils.notifier.requests") as mock_requests:
            mock_requests.post.side_effect = Exception("Network error")

            result = send_stop_loss_notification(
                webhook_url="https://hooks.slack.com/services/test",
                kind=StopLossEventKind.ARMED,
                level=1,
                current_price=Decimal("75000000"),
                threshold=Decimal("80000000"),
                lower_price=Decimal("100000000"),
                symbol="KRW-BTC",
            )

            self.assertTrue(result)

    def test_send_stop_loss_notification_requests_not_installed(self):
        """requests 모듈 미설치: 경고 로그하고 True 반환"""
        with patch("app.utils.notifier.requests", None):
            result = send_stop_loss_notification(
                webhook_url="https://hooks.slack.com/services/test",
                kind=StopLossEventKind.ARMED,
                level=1,
                current_price=Decimal("75000000"),
                threshold=Decimal("80000000"),
                lower_price=Decimal("100000000"),
                symbol="KRW-BTC",
            )

            self.assertTrue(result)

    def test_build_webhook_payload_armed(self):
        """ARMED 페이로드 구성"""
        payload = _build_webhook_payload(
            kind=StopLossEventKind.ARMED,
            level=1,
            current_price=Decimal("75000000"),
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            symbol="KRW-BTC",
            liquidated_qty=None,
            failed_slots=None,
        )

        self.assertIn("attachments", payload)
        attachment = payload["attachments"][0]
        self.assertEqual(attachment["color"], "#FFA500")  # 주황색
        self.assertIn("L1", attachment["title"])
        self.assertIn("손절", attachment["title"])

    def test_build_webhook_payload_executed(self):
        """EXECUTED 페이로드 구성"""
        payload = _build_webhook_payload(
            kind=StopLossEventKind.EXECUTED,
            level=2,
            current_price=Decimal("65000000"),
            threshold=Decimal("70000000"),
            lower_price=Decimal("100000000"),
            symbol="KRW-BTC",
            liquidated_qty=Decimal("0.005"),
            failed_slots=None,
        )

        attachment = payload["attachments"][0]
        self.assertEqual(attachment["color"], "#36A64F")  # 초록색
        self.assertIn("청산 완료", attachment["title"])
        self.assertIn("임계값", attachment["text"])
        self.assertIn("70000000", attachment["text"])

    def test_build_webhook_payload_failed(self):
        """FAILED 페이로드 구성"""
        payload = _build_webhook_payload(
            kind=StopLossEventKind.FAILED,
            level=1,
            current_price=Decimal("75000000"),
            threshold=Decimal("80000000"),
            lower_price=Decimal("100000000"),
            symbol="KRW-BTC",
            liquidated_qty=None,
            failed_slots=[0, 2, 4],
        )

        attachment = payload["attachments"][0]
        self.assertEqual(attachment["color"], "#FF0000")  # 빨강색
        self.assertIn("실패", attachment["title"])
        self.assertIn("임계값", attachment["text"])
        self.assertIn("80000000", attachment["text"])


if __name__ == "__main__":
    unittest.main()
