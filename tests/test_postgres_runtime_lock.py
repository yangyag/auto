import unittest

from storage.postgres_common import PostgresRuntimeLock
from tests.postgres_test_utils import (
    PostgresIntegrationTestCase,
    apply_test_schema,
    drop_test_schema,
    postgres_test_config,
)


class PostgresRuntimeLockTest(PostgresIntegrationTestCase):
    def setUp(self):
        self.config = postgres_test_config()
        apply_test_schema(self.config.PGSCHEMA)

    def tearDown(self):
        drop_test_schema(self.config.PGSCHEMA)

    def test_runtime_lock_allows_only_one_holder_per_bot_key(self):
        first = PostgresRuntimeLock.from_config(self.config)
        second = PostgresRuntimeLock.from_config(self.config)

        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()


if __name__ == "__main__":
    unittest.main()
