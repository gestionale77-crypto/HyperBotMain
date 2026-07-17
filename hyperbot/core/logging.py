from __future__ import annotations

import logging
import sys
from typing import Any


def configure_logging(log_level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logger = logging.getLogger("hyperbot")
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class StructuredLogMixin:
    @property
    def logger(self) -> logging.Logger:
        return get_logger(self.__class__.__module__)

    def log_event(self, event: str, **context: Any) -> None:
        self.logger.info("event=%s context=%s", event, context)
