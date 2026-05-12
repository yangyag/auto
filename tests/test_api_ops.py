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
        self.assertIn("실현손익", body)
        self.assertIn("/v1/auth/login", body)
        self.assertIn("/v1/bot/status", body)
        self.assertIn("/v1/grid/summary", body)
        self.assertIn("/v1/market/price", body)
        self.assertIn("/v1/pnl/realized?period=", body)
        self.assertNotIn("/v1/commands/reset", body)
        self.assertNotIn("Bot Status", body)
        self.assertNotIn("Grid Summary", body)
        self.assertNotIn("Realized PnL", body)


if __name__ == "__main__":
    unittest.main()
