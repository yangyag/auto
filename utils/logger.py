"""
공용 로거
"""
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def current_kst_datetime() -> datetime:
    return datetime.now(tz=KST)


class KSTFormatter(logging.Formatter):
    """서버 로컬 시간대와 무관하게 로그 시간을 KST로 포맷한다."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=KST)
        if datefmt:
            return timestamp.strftime(datefmt)
        return timestamp.isoformat(timespec="seconds")


class DailyFileHandler(logging.Handler):
    """KST 날짜가 바뀌면 새 파일로 전환하는 일별 파일 핸들러."""

    def __init__(
        self,
        log_dir: str | Path,
        log_file: str,
        *,
        encoding: str = "utf-8",
        date_provider=None,
        retention_days: int = 3,
    ):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_file = Path(log_file)
        self.encoding = encoding
        self.date_provider = date_provider or (lambda: current_kst_datetime().strftime("%Y-%m-%d"))
        self.retention_days = max(1, int(retention_days))
        self._current_date: str | None = None
        self._last_cleanup_date: str | None = None
        self._file_handler: logging.FileHandler | None = None

    def _build_daily_path(self, date_str: str) -> Path:
        stem = self.log_file.stem or self.log_file.name
        suffix = self.log_file.suffix or ".log"
        return self.log_dir / f"{stem}-{date_str}{suffix}"

    @staticmethod
    def _parse_date(date_str: str) -> date:
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    def _cleanup_old_logs(self, current_date: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)

        current_day = self._parse_date(current_date)
        delete_before = current_day - timedelta(days=self.retention_days)
        stem = self.log_file.stem or self.log_file.name
        suffix = self.log_file.suffix or ".log"
        prefix = f"{stem}-"
        active_path = (
            Path(self._file_handler.baseFilename)
            if self._file_handler is not None
            else self._build_daily_path(current_date)
        ).resolve()

        for path in self.log_dir.glob(f"{prefix}*{suffix}"):
            if not path.is_file() or path.resolve() == active_path:
                continue

            date_text = path.name[len(prefix):-len(suffix)]
            try:
                file_day = self._parse_date(date_text)
            except ValueError:
                continue

            if file_day > delete_before:
                continue

            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as exc:
                # 로그 정리 실패가 거래 루프를 막지 않도록 stderr에만 남긴다.
                sys.stderr.write(f"오래된 로그 삭제 실패: {path} ({exc})\n")
                continue

    def _ensure_handler(self) -> None:
        current_date = self.date_provider()

        if self._last_cleanup_date != current_date:
            self._cleanup_old_logs(current_date)
            self._last_cleanup_date = current_date

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
    from config.settings import LOG_DIR, LOG_FILE, LOG_LEVEL, LOG_RETENTION_DAYS

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = KSTFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 출력
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 날짜별 파일 출력: logs/trading-YYYY-MM-DD.log (KST 기준)
    fh = DailyFileHandler(
        LOG_DIR,
        LOG_FILE,
        encoding="utf-8",
        retention_days=LOG_RETENTION_DAYS,
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.propagate = False

    return logger
