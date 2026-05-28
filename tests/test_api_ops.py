import unittest

from app.api.main import create_app
from app.api.routers.ops import ops_dashboard


class MobileApiOpsDashboardTest(unittest.TestCase):
    def test_ops_route_is_registered_outside_openapi_schema(self):
        app = create_app()
        routes = {route.path: route for route in app.routes}

        self.assertIn("/ops", routes)
        self.assertFalse(routes["/ops"].include_in_schema)

    def test_ops_dashboard_contains_read_only_checks(self):
        response = ops_dashboard()
        body = response.body.decode("utf-8")

        self.assertIn("auto API 점검", body)
        self.assertIn("접속 정보", body)
        self.assertIn("빠른 조회", body)
        self.assertIn("봇 상태", body)
        self.assertIn("그리드 요약", body)
        self.assertIn("그리드 전체", body)
        self.assertIn("계획 매수(KRW)", body)
        self.assertIn("보유 원가(KRW)", body)
        self.assertIn("유효 매도가", body)
        self.assertIn("실현손익", body)
        self.assertIn("/v1/auth/login", body)
        self.assertIn("/v1/bot/status", body)
        self.assertIn("/v1/grid/summary", body)
        self.assertIn("/v1/grid/state", body)
        self.assertIn("/v1/market/price", body)
        self.assertIn("/v1/pnl/realized?period=", body)
        self.assertNotIn("/v1/commands/reset", body)
        self.assertNotIn("Bot Status", body)
        self.assertNotIn("Grid Summary", body)
        self.assertNotIn("Realized PnL", body)

    def test_ops_dashboard_monitor_has_no_hardcoded_btc_header(self):
        """renderMonitorTable must derive base currency from data.market, not hardcode BTC."""
        response = ops_dashboard()
        body = response.body.decode("utf-8")

        self.assertIn("/v1/monitor/open-sells", body)
        self.assertNotIn('"수량(BTC)"', body)
        self.assertIn("market.includes", body)
        self.assertIn("baseCurrency", body)


class MonitorRouterDefaultMarketTest(unittest.TestCase):
    def test_open_sells_market_default_is_cfg_symbol_not_hardcoded(self):
        """GET /v1/monitor/open-sells market default must be cfg.SYMBOL, not 'KRW-BTC'."""
        import app.config.settings as cfg
        from app.api.routers.monitor import open_sells

        default = open_sells.__defaults__[0]
        self.assertEqual(default.default, cfg.SYMBOL)
        self.assertNotEqual(default.default, "KRW-BTC")

    def test_open_sells_bot_key_default_is_none_passthrough(self):
        """bot_key default is None so service layer can apply cfg.STATE_BOT_KEY."""
        from app.api.routers.monitor import open_sells

        default = open_sells.__defaults__[2]
        self.assertIsNone(default.default)


if __name__ == "__main__":
    unittest.main()
