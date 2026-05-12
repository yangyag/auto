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

        self.assertIn("/v1/auth/login", body)
        self.assertIn("/v1/bot/status", body)
        self.assertIn("/v1/grid/summary", body)
        self.assertIn("/v1/market/price", body)
        self.assertIn("/v1/pnl/realized?period=", body)
        self.assertNotIn("/v1/commands/reset", body)


if __name__ == "__main__":
    unittest.main()
