"""
Shared logging configuration for Voice to Text (Windows & macOS).

Provides both rich terminal output and rotating file-based logging.
Logs are saved to outputs/ directory with automatic rotation.
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from rich.console import Console
from typing import Optional

# Create outputs directory in project root if it doesn't exist
OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Configure rich console for colored output
console = Console()

# Determine log file path based on which script is running
# This will be windows.log or macos.log
import sys
script_name = "windows" if "voice_to_text_windows" in sys.argv[0] else "macos"
LOG_FILE = OUTPUTS_DIR / f"{script_name}.log"

# Maximum log file size (10 MB) before rotation
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB

# Number of backup log files to keep
BACKUP_COUNT = 5


def setup_logger(name: str = "voice_to_text") -> logging.Logger:
    """Setup and return a configured logger with both terminal and file output.

    Creates a logger that outputs to:
    1. Console with rich formatting and colors
    2. Rotating file handler in outputs/ directory

    Args:
        name: Logger name (default: "voice_to_text").

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Rich handler for terminal (DEBUG level and above, with colors)
    # Individual handler level will be overridden by logger level
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        level=logging.DEBUG
    )
    rich_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(rich_handler)

    # Rotating file handler (DEBUG level and above, for traceability)
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not setup file logging to {LOG_FILE}: {e}[/]")

    return logger


def get_outputs_dir() -> Path:
    """Get the outputs directory path.

    Returns:
        Path object for outputs directory.
    """
    return OUTPUTS_DIR


def print_log_location() -> None:
    """Print the log file location to the console."""
    log_file_abs = LOG_FILE.resolve()
    console.print(f"[dim]Logs saved to: {log_file_abs}[/]")
