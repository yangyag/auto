"""
공용 로거
"""
import logging
import sys
from datetime import datetime
from pathlib import Path


class DailyFileHandler(logging.Handler):
    """로컬 날짜가 바뀌면 새 파일로 전환하는 일별 파일 핸들러."""

    def __init__(
        self,
        log_dir: str | Path,
        log_file: str,
        *,
        encoding: str = "utf-8",
        date_provider=None,
    ):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_file = Path(log_file)
        self.encoding = encoding
        self.date_provider = date_provider or (lambda: datetime.now().strftime("%Y-%m-%d"))
        self._current_date: str | None = None
        self._file_handler: logging.FileHandler | None = None

    def _build_daily_path(self, date_str: str) -> Path:
        stem = self.log_file.stem or self.log_file.name
        suffix = self.log_file.suffix or ".log"
        return self.log_dir / f"{stem}-{date_str}{suffix}"

    def _ensure_handler(self) -> None:
        current_date = self.date_provider()
        if self._file_handler is not None and self._current_date == current_date:
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)

        if self._file_handler is not None:
            self._file_handler.close()

        self._current_date = current_date
        self._file_handler = logging.FileHandler(
            self._build_daily_path(current_date),
            encoding=self.encoding,
        )
        if self.formatter is not None:
            self._file_handler.setFormatter(self.formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_handler()
            if self._file_handler is not None:
                self._file_handler.emit(record)
        except Exception:
            self.handleError(record)

    def setFormatter(self, fmt: logging.Formatter) -> None:
        super().setFormatter(fmt)
        if self._file_handler is not None:
            self._file_handler.setFormatter(fmt)

    def flush(self) -> None:
        if self._file_handler is not None:
            self._file_handler.flush()

    def close(self) -> None:
        try:
            if self._file_handler is not None:
                self._file_handler.close()
                self._file_handler = None
        finally:
            super().close()


def get_logger(name: str) -> logging.Logger:
    from config.settings import LOG_DIR, LOG_FILE, LOG_LEVEL

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 출력
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 날짜별 파일 출력: logs/trading-YYYY-MM-DD.log
    fh = DailyFileHandler(LOG_DIR, LOG_FILE, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.propagate = False

    return logger
