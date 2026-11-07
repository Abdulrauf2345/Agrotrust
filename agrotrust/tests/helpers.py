"""Shared test fixtures (stdlib unittest; also collected natively by pytest)."""
from __future__ import annotations

import os
import tempfile
import unittest

from agrotrust.db.database import Database
from agrotrust.shared.clock import FrozenClock


class DbTestCase(unittest.TestCase):
    """Fresh on-disk SQLite database per test (file-based so threads get real connections)."""

    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.db_path)
        self.db.init_schema()
        self.clock = FrozenClock()

    def tearDown(self) -> None:
        self.db.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.db_path + suffix)
            except (FileNotFoundError, PermissionError):
                pass   # best-effort cleanup; a stray OS-level file lock shouldn't fail the test
