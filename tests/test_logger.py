import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.logger import DailyFileHandler


class DailyFileHandlerTest(unittest.TestCase):
    def _build_handler(self, tmpdir: str, *, date_provider):
        handler = DailyFileHandler(
            tmpdir,
            "trading.log",
            date_provider=date_provider,
            retention_days=7,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def _build_logger(self, handler: DailyFileHandler) -> logging.Logger:
        logger = logging.getLogger(f"tests.daily_file_handler.{self._testMethodName}")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        self.addCleanup(handler.close)
        self.addCleanup(logger.handlers.clear)
        return logger

    def test_daily_file_handler_writes_to_date_named_files(self):
        date_values = iter([
            "2026-04-14",
            "2026-04-14",
            "2026-04-15",
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = self._build_handler(tmpdir, date_provider=lambda: next(date_values))
            logger = self._build_logger(handler)

            logger.info("프로그램 시작")
            logger.info("매수 체결")
            logger.info("매도 체결")
            handler.flush()

            day1_path = Path(tmpdir) / "trading-2026-04-14.log"
            day2_path = Path(tmpdir) / "trading-2026-04-15.log"

            self.assertEqual(day1_path.read_text(encoding="utf-8").splitlines(), ["프로그램 시작", "매수 체결"])
            self.assertEqual(day2_path.read_text(encoding="utf-8").splitlines(), ["매도 체결"])

    def test_daily_file_handler_deletes_logs_older_than_seven_days_on_emit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = Path(tmpdir) / "trading-2026-04-07.log"
            retained_path = Path(tmpdir) / "trading-2026-04-08.log"
            old_path.write_text("too old", encoding="utf-8")
            retained_path.write_text("keep me", encoding="utf-8")

            handler = self._build_handler(tmpdir, date_provider=lambda: "2026-04-14")
            logger = self._build_logger(handler)

            logger.info("cleanup trigger")
            handler.flush()

            today_path = Path(tmpdir) / "trading-2026-04-14.log"

            self.assertFalse(old_path.exists())
            self.assertTrue(retained_path.exists())
            self.assertEqual(today_path.read_text(encoding="utf-8").splitlines(), ["cleanup trigger"])

    def test_daily_file_handler_cleans_up_again_after_day_rollover_without_restart(self):
        current_date = ["2026-04-14"]

        with tempfile.TemporaryDirectory() as tmpdir:
            boundary_path = Path(tmpdir) / "trading-2026-04-08.log"
            boundary_path.write_text("keep on day 1", encoding="utf-8")

            handler = self._build_handler(tmpdir, date_provider=lambda: current_date[0])
            logger = self._build_logger(handler)

            logger.info("day 1 cleanup")
            handler.flush()
            self.assertTrue(boundary_path.exists())

            current_date[0] = "2026-04-15"
            logger.info("day 2 cleanup")
            handler.flush()

            self.assertFalse(boundary_path.exists())
            self.assertTrue((Path(tmpdir) / "trading-2026-04-14.log").exists())
            self.assertTrue((Path(tmpdir) / "trading-2026-04-15.log").exists())

    def test_daily_file_handler_ignores_non_matching_or_invalid_log_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deleted_path = Path(tmpdir) / "trading-2026-04-06.log"
            untouched_paths = [
                Path(tmpdir) / "trading.log",
                Path(tmpdir) / "trading-latest.log",
                Path(tmpdir) / "other-2026-04-01.log",
                Path(tmpdir) / "trading-2026-13-01.log",
            ]
            deleted_path.write_text("old log", encoding="utf-8")
            for path in untouched_paths:
                path.write_text("leave me alone", encoding="utf-8")

            handler = self._build_handler(tmpdir, date_provider=lambda: "2026-04-14")
            logger = self._build_logger(handler)

            logger.info("cleanup trigger")
            handler.flush()

            self.assertFalse(deleted_path.exists())
            for path in untouched_paths:
                self.assertTrue(path.exists(), msg=f"{path.name} should not be deleted")

    def test_daily_file_handler_does_not_delete_active_file_while_it_is_open(self):
        current_date = ["2026-04-07"]

        with tempfile.TemporaryDirectory() as tmpdir:
            current_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                active_path = Path("logs") / "trading-2026-04-07.log"
                handler = self._build_handler("logs", date_provider=lambda: current_date[0])
                logger = self._build_logger(handler)

                logger.info("day 1 log")
                handler.flush()
                self.assertTrue(active_path.exists())

                current_date[0] = "2026-04-15"
                with patch("os.unlink", wraps=os.unlink) as unlink_mock:
                    logger.info("day 2 log")
                    handler.flush()

                deleted_paths = {Path(call.args[0]).resolve() for call in unlink_mock.call_args_list}
                self.assertTrue(active_path.exists())
                self.assertNotIn(active_path.resolve(), deleted_paths)
            finally:
                os.chdir(current_dir)


if __name__ == "__main__":
    unittest.main()
