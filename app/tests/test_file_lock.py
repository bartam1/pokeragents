"""
Tests for file locking utilities.

These tests verify that file locking works correctly to prevent
race conditions when multiple processes access shared files.

Note: fcntl locks work at the process level, not thread level.
Cross-process locking is the main use case and is tested manually
by running multiple tournament processes.
"""

import os
import tempfile
from pathlib import Path

from backend.domain.utils.file_lock import file_lock, stats_file_lock


class TestFileLock:
    """Test the file_lock context manager."""

    def test_lock_creates_lock_file(self):
        """Lock file should be created next to the target file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test.json")
            lock_path = target + ".lock"

            # Lock file shouldn't exist yet
            assert not os.path.exists(lock_path)

            with file_lock(target):
                # Lock file should exist during lock
                assert os.path.exists(lock_path)

    def test_can_acquire_and_release_lock(self):
        """Basic lock acquire and release should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test.json")

            # First acquisition
            with file_lock(target, exclusive=True):
                Path(target).write_text('{"test": 1}')

            # Should be able to acquire again after release
            with file_lock(target, exclusive=True):
                data = Path(target).read_text()
                assert data == '{"test": 1}'

    def test_shared_lock_allows_read(self):
        """Shared lock should allow reading."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test.json")
            Path(target).write_text('{"data": "value"}')

            with file_lock(target, exclusive=False):
                data = Path(target).read_text()
                assert "data" in data


class TestStatsFileLock:
    """Test the stats_file_lock convenience wrapper."""

    def test_stats_lock_exclusive(self):
        """stats_file_lock with exclusive=True should block other exclusive locks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")

            # Write some test data
            Path(stats_path).write_text("{}")

            with stats_file_lock(stats_path, exclusive=True):
                # Should be able to read/write while holding lock
                data = Path(stats_path).read_text()
                assert data == "{}"

    def test_stats_lock_shared(self):
        """stats_file_lock with exclusive=False should allow concurrent reads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")
            Path(stats_path).write_text('{"test": true}')

            with stats_file_lock(stats_path, exclusive=False):
                data = Path(stats_path).read_text()
                assert "test" in data


class TestLockEdgeCases:
    """Edge cases and error handling."""

    def test_lock_on_nonexistent_file(self):
        """Should be able to lock a file that doesn't exist yet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "nonexistent.json")

            # File doesn't exist
            assert not os.path.exists(target)

            # But we can still lock it
            with file_lock(target):
                # Lock acquired successfully
                pass

    def test_lock_creates_parent_directories(self):
        """Lock should create parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "subdir", "nested", "test.json")

            # Parent dirs don't exist
            assert not os.path.exists(os.path.dirname(target))

            with file_lock(target):
                # Parent dirs should be created for lock file
                assert os.path.exists(os.path.dirname(target))

    def test_lock_released_on_exception(self):
        """Lock should be released even if an exception occurs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test.json")

            try:
                with file_lock(target):
                    raise ValueError("Test exception")
            except ValueError:
                pass

            # Should be able to acquire lock again (it was released)
            with file_lock(target):
                pass  # No deadlock
