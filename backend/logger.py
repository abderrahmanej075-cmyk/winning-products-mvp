"""Structured JSON logging configuration."""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict

from config import settings


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                # Skip default logging attributes
                if key not in {
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "message", "pathname", "process", "processName", "relativeCreated",
                    "thread", "threadName", "exc_info", "exc_text", "stack_info", "taskName"
                }:
                    log_data[key] = value

        return json.dumps(log_data)


def setup_logger() -> logging.Logger:
    """Configure and return a logger with JSON formatting."""
    logger = logging.getLogger("winning_products")

    # Remove any existing handlers
    logger.handlers.clear()

    # Set log level from config
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    formatter = JSONFormatter()
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


# Create logger instance
logger = setup_logger()


def get_logger(name: str = "winning_products") -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)
