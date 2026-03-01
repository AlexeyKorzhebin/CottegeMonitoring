"""structlog configuration with JSON output + RotatingFileHandler."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

import structlog

from cottage_monitoring.config import settings


def setup_logging() -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.processors.JSONRenderer()],
        foreign_pre_chain=shared_processors,
    )

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # stdout handler (for Docker / journald)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # file handlers (if log dir exists or can be created)
    log_dir = settings.log_dir
    try:
        os.makedirs(log_dir, exist_ok=True)
        _add_file_handler(root, formatter, os.path.join(log_dir, "app.log"), level)
        _add_file_handler(
            logging.getLogger("cottage_monitoring.mqtt"),
            formatter,
            os.path.join(log_dir, "mqtt.log"),
            level,
        )
    except OSError:
        root.warning("Cannot create log directory %s, file logging disabled", log_dir)


def _add_file_handler(
    logger: logging.Logger,
    formatter: logging.Formatter,
    path: str,
    level: int,
) -> None:
    handler = RotatingFileHandler(
        path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    logger.addHandler(handler)
