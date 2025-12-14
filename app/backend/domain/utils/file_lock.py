"""
File locking utilities for safe concurrent access.

Provides cross-process file locking to prevent race conditions when
multiple tournament processes read/write shared files like stats.json.
"""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from backend.logging_config import get_logger

logger = get_logger(__name__)


@contextmanager
def file_lock(
    file_path: str,
    exclusive: bool = True,
    timeout: float | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for file locking.

    Uses fcntl for Unix file locking. Creates a .lock file next to the target
    to avoid issues with the target file being recreated.

    Args:
        file_path: Path to the file to lock
        exclusive: If True, use exclusive lock (write). If False, shared lock (read).
        timeout: Not implemented yet - locks are blocking.

    Usage:
        with file_lock("data/knowledge/stats.json"):
            # Safe to read/write stats.json
            data = load_stats()
            save_stats(data)

    Note:
        - Locks are advisory - all processes must use this utility
        - Lock is released automatically when context exits
        - Works across processes, not just threads
    """
    lock_path = str(file_path) + ".lock"

    # Ensure parent directory exists
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)

    lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    lock_name = "exclusive" if exclusive else "shared"

    # Open lock file (create if doesn't exist)
    lock_file = open(lock_path, "w")

    try:
        logger.debug(f"Acquiring {lock_name} lock on {file_path}")
        fcntl.flock(lock_file.fileno(), lock_type)
        logger.debug(f"Acquired {lock_name} lock on {file_path}")

        yield

    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        logger.debug(f"Released {lock_name} lock on {file_path}")


@contextmanager
def stats_file_lock(
    stats_path: str,
    exclusive: bool = True,
) -> Generator[None, None, None]:
    """
    Convenience wrapper for locking the stats.json file.

    Args:
        stats_path: Path to stats.json
        exclusive: True for writing, False for reading

    Usage:
        # For writing (recalculating stats):
        with stats_file_lock(stats_path, exclusive=True):
            recalculate_and_save_stats()

        # For reading (loading stats):
        with stats_file_lock(stats_path, exclusive=False):
            kb = KnowledgeBase.load_from_file(stats_path)
    """
    with file_lock(stats_path, exclusive=exclusive):
        yield

