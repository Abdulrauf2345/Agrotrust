"""Regression test for a real bug found when running on Windows: Database.close() only closed
the calling thread's connection, leaving worker-thread connections open and the underlying file
locked (Windows refuses to delete an open file; POSIX does not, which is why this went
unnoticed when the project was only run on Linux)."""
import os
import tempfile
import threading
import unittest

from agrotrust.db.database import Database


class DatabaseCleanupTests(unittest.TestCase):
    def test_close_closes_connections_opened_by_other_threads(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(path)
        db.init_schema()

        opened_in_thread = []

        def touch_from_worker_thread():
            with db.transaction():
                db.execute("SELECT 1")
            opened_in_thread.append(True)

        threads = [threading.Thread(target=touch_from_worker_thread) for _ in range(5)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(opened_in_thread), 5)
        self.assertGreaterEqual(len(db._all_conns), 5)   # main thread's + each worker thread's

        db.close()
        self.assertEqual(db._all_conns, [])

        # The real-world symptom this bug caused: on Windows, deleting a file with any
        # connection still open raises PermissionError. We can't reproduce Windows' stricter
        # locking on Linux, but we can assert the fix's actual mechanism: zero connections
        # remain tracked/open after close(), regardless of which thread opened them.
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass

    def test_close_is_safe_to_call_twice(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = Database(path)
        db.init_schema()
        db.close()
        db.close()   # must not raise
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
