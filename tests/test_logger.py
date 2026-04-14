import logging
import tempfile
import unittest
from pathlib import Path

from utils.logger import DailyFileHandler


class DailyFileHandlerTest(unittest.TestCase):

    def test_daily_file_handler_writes_to_date_named_files(self):
        date_values = iter([
            "2026-04-14",
            "2026-04-14",
            "2026-04-15",
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = DailyFileHandler(
                tmpdir,
                "trading.log",
                date_provider=lambda: next(date_values),
            )
            handler.setFormatter(logging.Formatter("%(message)s"))

            logger = logging.getLogger("tests.daily_file_handler")
            logger.handlers.clear()
            logger.setLevel(logging.INFO)
            logger.propagate = False
            logger.addHandler(handler)

            logger.info("프로그램 시작")
            logger.info("매수 체결")
            logger.info("매도 체결")

            handler.close()
            logger.handlers.clear()

            day1_path = Path(tmpdir) / "trading-2026-04-14.log"
            day2_path = Path(tmpdir) / "trading-2026-04-15.log"

            self.assertEqual(day1_path.read_text(encoding="utf-8").splitlines(), ["프로그램 시작", "매수 체결"])
            self.assertEqual(day2_path.read_text(encoding="utf-8").splitlines(), ["매도 체결"])


if __name__ == "__main__":
    unittest.main()
