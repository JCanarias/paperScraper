"""Tells whether the daily check is running, so it and the menu don't write the same lists at once.

The lock is held by the operating system while the daily check runs: if the program crashes or
the machine restarts, it is gone, and the next run doesn't find an old lock left behind.
"""
from pathlib import Path
from typing import IO

LOCK_FILE = Path("library") / ".daily_check.lock"


def take_daily_lock() -> IO | None:
    """Take the lock and return its file (keep it open while running), or None if another run has it."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(LOCK_FILE, "a+")
    try:
        _lock(lock_file)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def daily_check_running() -> bool:
    lock_file = take_daily_lock()
    if lock_file is None:
        return True
    _unlock(lock_file)
    lock_file.close()
    return False


try:
    import fcntl

    def _lock(lock_file: IO) -> None:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(lock_file: IO) -> None:
        fcntl.flock(lock_file, fcntl.LOCK_UN)

except ImportError:  # Windows
    import msvcrt

    def _lock(lock_file: IO) -> None:
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(lock_file: IO) -> None:
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
