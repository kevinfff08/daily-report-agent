"""Centralized logging configuration for DailyReport."""

import logging
from datetime import date, datetime
from pathlib import Path

_INITIALIZED = False
_LOG_DIR = Path("logs")
_ROOT_LOGGER_NAME = "dailyreport"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-35s | %(message)s"


def log_month_dir(target_date: date) -> Path:
    """Return the YYYY-MM log subdirectory for a given date."""
    return Path(target_date.strftime("%Y-%m"))


def log_file_path(target_date: date, log_dir: str | Path | None = None) -> Path:
    """Return the full log file path for a given date."""
    base_dir = Path(log_dir) if log_dir else _LOG_DIR
    return base_dir / log_month_dir(target_date) / f"{target_date.isoformat()}.log"


def setup_logging(log_dir: str | Path | None = None) -> None:
    """Initialize logging with daily rotating file and console output.

    Safe to call multiple times; only initializes once.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    target_date = datetime.now().date()
    log_file = log_file_path(target_date, log_dir)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(logging.DEBUG)

    # File handler: DEBUG level (all messages)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Console handler: WARNING+ only
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(formatter)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the dailyreport namespace."""
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")
