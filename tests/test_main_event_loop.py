import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import main
from core.models import Order, OrderSide
from exchange.upbit_ws import UpbitTickerPriceEvent
from storage.interfaces import RepositoryMetadata
from strategy.breakout_guard import BreakoutGuardStatus


class FakePriceEventExchange:
    def __init__(
        self,
        *,
        wait_event: UpbitTickerPriceEvent | None,
        latest_event: UpbitTickerPriceEvent | None = None,
    ):
        self.wait_event = wait_event
        self.latest_event = latest_event
        self.wait_calls = []

    def wait_for_ticker_price_event(self, symbol: str, *, timeout: float, since: float | None):
        self.wait_calls.append((symbol, timeout, since))
        return self.wait_event

    def get_ticker_price_event(self, symbol: str):
        return self.latest_event


class MainEventLoopTest(unittest.TestCase):

    def _cycle_kwargs(self):
        return {
            "strategy": Mock(),
            "grid_state": Mock(),
            "grid_repository": Mock(),
            "runtime": main.GridStateRuntime(),
            "pending_orders": {},
            "current_order_day": date(2026, 4, 24),
            "daily_order_count": 0,
            "on_grid_updated": Mock(),
            "pending_order_repository": Mock(),
        }

    def test_price_event_loop_runs_cycle_immediately_on_price_event(self):
        event = UpbitTickerPriceEvent(
            symbol="KRW-BTC",
            price=Decimal("101"),
            updated_at=10.0,
        )
        exchange = FakePriceEventExchange(wait_event=event, latest_event=event)
        price_event_state = main.PriceEventLoopState()
        sleep_calls = []

        with patch.object(
            main,
            "run_trading_cycle",
            return_value=main.TradingCycleResult(date(2026, 4, 24), 0),
        ) as run_cycle:
            main.run_price_event_loop_iteration(
                exchange=exchange,
                price_event_state=price_event_state,
                wait_timeout_seconds=5,
                min_interval_seconds=3,
                time_provider=lambda: 100.0,
                sleep_fn=sleep_calls.append,
                **self._cycle_kwargs(),
            )

        self.assertEqual(sleep_calls, [])
        self.assertEqual(exchange.wait_calls, [("KRW-BTC", 5.0, None)])
        self.assertEqual(price_event_state.last_event_at, 10.0)
        run_cycle.assert_called_once()
        self.assertEqual(run_cycle.call_args.kwargs["current_price"], Decimal("101"))
        self.assertNotIn("force_rest_price", run_cycle.call_args.kwargs)

    def test_price_event_loop_throttles_to_minimum_interval_and_uses_latest_price(self):
        first_event = UpbitTickerPriceEvent(
            symbol="KRW-BTC",
            price=Decimal("101"),
            updated_at=10.0,
        )
        latest_event = UpbitTickerPriceEvent(
            symbol="KRW-BTC",
            price=Decimal("102"),
            updated_at=11.0,
        )
        exchange = FakePriceEventExchange(wait_event=first_event, latest_event=latest_event)
        price_event_state = main.PriceEventLoopState(last_cycle_at=100.0)
        sleep_calls = []

        with patch.object(
            main,
            "run_trading_cycle",
            return_value=main.TradingCycleResult(date(2026, 4, 24), 0),
        ) as run_cycle:
            main.run_price_event_loop_iteration(
                exchange=exchange,
                price_event_state=price_event_state,
                wait_timeout_seconds=5,
                min_interval_seconds=3,
                time_provider=lambda: 101.0,
                sleep_fn=sleep_calls.append,
                **self._cycle_kwargs(),
            )

        self.assertEqual(sleep_calls, [2.0])
        self.assertEqual(price_event_state.last_event_at, 11.0)
        self.assertEqual(run_cycle.call_args.kwargs["current_price"], Decimal("102"))

    def test_price_event_loop_waits_for_newer_event_when_throttle_sleep_leaves_stale_price(self):
        """throttle sleep 후에도 더 최신 WS 이벤트가 없으면 낡은 가격으로 평가하지
        않도록 min_interval 만큼 추가 대기한 뒤 새 이벤트로 평가해야 한다."""
        first_event = UpbitTickerPriceEvent(
            symbol="KRW-BTC", price=Decimal("101"), updated_at=10.0
        )
        newer_event = UpbitTickerPriceEvent(
            symbol="KRW-BTC", price=Decimal("103"), updated_at=11.5
        )

        exchange = Mock()
        # 첫 wait → first_event (since=None), 추가 대기 → newer_event (since=10.0)
        exchange.wait_for_ticker_price_event.side_effect = [first_event, newer_event]
        # throttle sleep 후 latest 캐시는 아직 first_event
        exchange.get_ticker_price_event.return_value = first_event
        price_event_state = main.PriceEventLoopState(last_cycle_at=100.0)
        sleep_calls = []

        with patch.object(
            main,
            "run_trading_cycle",
            return_value=main.TradingCycleResult(date(2026, 4, 24), 0),
        ) as run_cycle:
            main.run_price_event_loop_iteration(
                exchange=exchange,
                price_event_state=price_event_state,
                wait_timeout_seconds=5,
                min_interval_seconds=3,
                time_provider=lambda: 101.0,  # elapsed_since_cycle=1 → throttle_sleep=2
                sleep_fn=sleep_calls.append,
                **self._cycle_kwargs(),
            )

        self.assertEqual(sleep_calls, [2.0])
        self.assertEqual(exchange.wait_for_ticker_price_event.call_count, 2)
        extra_call = exchange.wait_for_ticker_price_event.call_args_list[1]
        self.assertEqual(extra_call.kwargs, {"timeout": 3.0, "since": 10.0})
        self.assertEqual(run_cycle.call_args.kwargs["current_price"], Decimal("103"))
        self.assertNotIn("force_rest_price", run_cycle.call_args.kwargs)
        self.assertEqual(price_event_state.last_event_at, 11.5)

    def test_price_event_loop_falls_back_to_rest_when_throttle_extra_wait_timeouts(self):
        """throttle sleep + 추가 대기까지 새 이벤트가 없으면 REST fallback 으로
        cycle 을 진행하고 last_event_at 은 건드리지 않는다."""
        stale_event = UpbitTickerPriceEvent(
            symbol="KRW-BTC", price=Decimal("101"), updated_at=10.0
        )

        exchange = Mock()
        exchange.wait_for_ticker_price_event.side_effect = [stale_event, None]
        exchange.get_ticker_price_event.return_value = stale_event
        price_event_state = main.PriceEventLoopState(last_cycle_at=100.0, last_event_at=9.0)
        sleep_calls = []

        with patch.object(
            main,
            "run_trading_cycle",
            return_value=main.TradingCycleResult(date(2026, 4, 24), 0),
        ) as run_cycle:
            main.run_price_event_loop_iteration(
                exchange=exchange,
                price_event_state=price_event_state,
                wait_timeout_seconds=5,
                min_interval_seconds=3,
                time_provider=lambda: 101.0,
                sleep_fn=sleep_calls.append,
                **self._cycle_kwargs(),
            )

        self.assertEqual(sleep_calls, [2.0])
        self.assertEqual(exchange.wait_for_ticker_price_event.call_count, 2)
        self.assertTrue(run_cycle.call_args.kwargs["force_rest_price"])
        self.assertEqual(price_event_state.last_event_at, 9.0)

    def test_price_event_loop_falls_back_to_rest_polling_when_event_unavailable(self):
        exchange = FakePriceEventExchange(wait_event=None)
        price_event_state = main.PriceEventLoopState()
        sleep_calls = []

        with patch.object(
            main,
            "run_trading_cycle",
            return_value=main.TradingCycleResult(date(2026, 4, 24), 0),
        ) as run_cycle:
            main.run_price_event_loop_iteration(
                exchange=exchange,
                price_event_state=price_event_state,
                wait_timeout_seconds=5,
                min_interval_seconds=3,
                time_provider=lambda: 200.0,
                sleep_fn=sleep_calls.append,
                **self._cycle_kwargs(),
            )

        self.assertEqual(sleep_calls, [5.0])
        self.assertTrue(run_cycle.call_args.kwargs["force_rest_price"])
        self.assertIsNone(price_event_state.last_event_at)

    def test_run_trading_cycle_preserves_order_processing_sequence(self):
        calls = []
        exchange = Mock()
        exchange.get_current_price.side_effect = lambda _symbol: calls.append("price") or Decimal("100")
        grid_state = Mock()
        grid_state.summary.return_value = "grid summary"
        grid_repository = Mock()
        grid_repository.has_changed.side_effect = lambda _metadata: calls.append("refresh") or False
        runtime = main.GridStateRuntime(metadata=RepositoryMetadata(version=1, revision="rev-1"))
        strategy = Mock()
        buy_order = Order(
            slot_index=1,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            symbol="KRW-BTC",
        )
        strategy.evaluate_with_pending.side_effect = (
            lambda _price, *, pending_slot_indexes: calls.append("evaluate") or ([buy_order], [])
        )

        with patch.object(
            main,
            "reconcile_pending_orders",
            side_effect=lambda *args, **kwargs: calls.append("reconcile") or 0,
        ), patch.object(
            main,
            "ensure_tp_sell_orders",
            side_effect=lambda **kwargs: calls.append("ensure_tp") or 0,
        ), patch.object(
            main,
            "fetch_breakout_guard_status",
            side_effect=lambda *_args, **_kwargs: calls.append("guard")
            or BreakoutGuardStatus(active=False, reason="inside_band"),
        ), patch.object(
            main,
            "process_cycle_orders",
            side_effect=lambda **kwargs: calls.append("process") or 1,
        ):
            result = main.run_trading_cycle(
                exchange=exchange,
                strategy=strategy,
                grid_state=grid_state,
                grid_repository=grid_repository,
                runtime=runtime,
                pending_orders={},
                current_order_day=date(2026, 4, 24),
                daily_order_count=0,
                on_grid_updated=Mock(),
                pending_order_repository=Mock(),
            )

        self.assertEqual(
            calls,
            ["refresh", "reconcile", "ensure_tp", "price", "guard", "evaluate", "process"],
        )
        self.assertEqual(result.daily_order_count, 1)

    def test_run_trading_cycle_force_rest_price_uses_rest_getter(self):
        calls = []
        exchange = Mock()
        exchange.get_current_price_rest.side_effect = (
            lambda _symbol: calls.append("rest_price") or Decimal("100")
        )
        exchange.get_current_price.side_effect = AssertionError("cached price path must not be used")
        grid_state = Mock()
        grid_state.summary.return_value = "grid summary"
        grid_repository = Mock()
        grid_repository.has_changed.return_value = False
        strategy = Mock()
        strategy.evaluate_with_pending.return_value = ([], [])

        with patch.object(main, "reconcile_pending_orders", return_value=0), \
             patch.object(main, "ensure_tp_sell_orders", return_value=0), \
             patch.object(
                 main,
                 "fetch_breakout_guard_status",
                 return_value=BreakoutGuardStatus(active=False, reason="inside_band"),
             ):
            main.run_trading_cycle(
                exchange=exchange,
                strategy=strategy,
                grid_state=grid_state,
                grid_repository=grid_repository,
                runtime=main.GridStateRuntime(),
                pending_orders={},
                current_order_day=date(2026, 4, 24),
                daily_order_count=0,
                on_grid_updated=Mock(),
                pending_order_repository=Mock(),
                force_rest_price=True,
            )

        self.assertEqual(calls, ["rest_price"])


if __name__ == "__main__":
    unittest.main()
