"""
Logging configuration for Karate Graph Analyzer.

Provides structured logging with configurable levels and formats.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    format_string: Optional[str] = None,
) -> None:
    """Set up structured logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARN, ERROR, CRITICAL)
        log_file: Optional log file name (if None, logs to console only)
        log_dir: Directory for log files
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep
        format_string: Custom log format string
    """
    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Default format with timestamp, level, component, and message
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        )

    # Create formatter
    formatter = logging.Formatter(
        format_string, datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation (if log_file specified)
    if log_file:
        # Create log directory if it doesn't exist
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set level for karate_graph_analyzer logger
    logger = logging.getLogger("karate_graph_analyzer")
    logger.setLevel(numeric_level)

    logger.info(f"Logging configured: level={level}, file={log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific component.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Predefined logging configurations
LOGGING_CONFIGS = {
    "development": {
        "level": "DEBUG",
        "log_file": "karate_analyzer_dev.log",
        "format_string": (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(funcName)s - %(message)s"
        ),
    },
    "production": {
        "level": "INFO",
        "log_file": "karate_analyzer.log",
        "format_string": (
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        ),
    },
    "testing": {
        "level": "WARNING",
        "log_file": None,  # Console only
        "format_string": "%(levelname)s - %(message)s",
    },
}


def setup_logging_from_config(config_name: str = "production") -> None:
    """Set up logging using a predefined configuration.

    Args:
        config_name: Name of configuration (development, production, testing)
    """
    if config_name not in LOGGING_CONFIGS:
        raise ValueError(
            f"Unknown config: {config_name}. "
            f"Available: {list(LOGGING_CONFIGS.keys())}"
        )

    config = LOGGING_CONFIGS[config_name]
    setup_logging(**config)


# Example usage:
if __name__ == "__main__":
    # Development logging
    setup_logging_from_config("development")

    logger = get_logger(__name__)
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
