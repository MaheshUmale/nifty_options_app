"""
Logger setup using loguru.
Single import point: `from utils.logger import get_logger`.
"""
import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_dir: str | Path | None = None, level: str = "INFO") -> None:
    """Configure loguru sinks (console + rotating file). Idempotent."""
    logger.remove()  # reset default
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSSSSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        logger.add(
            Path(log_dir) / "app_{time:YYYY-MM-DD}.log",
            level=level,
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,
        )


def get_logger():
    return logger
