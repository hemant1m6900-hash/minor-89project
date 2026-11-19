from __future__ import annotations

import logging
import sys

from backend.config import get_settings


def configure_logging() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger("commerceiq")
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger


logger = configure_logging()
