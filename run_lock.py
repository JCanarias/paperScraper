"""Tells whether the daily check is running, so it and the menu don't write the same lists at once.

The tasks of the web panel have their own lock: the daily check waits for them to end.

The lock is held by the operating system while the daily check runs: if the program crashes or
the machine restarts, it is gone, and the next run doesn't find an old lock left behind.
"""
from pathlib import Path
from typing import IO

from storage import LIBRARY_FOLDER

LOCK_FILE = LIBRARY_FOLDER / ".daily_check.lock"
PANEL_TASK_LOCK_FILE = LIBRARY_FOLDER / ".web" / "task.lock"


def take_daily_lock() -> IO | None:
    """Take the lock and return its file (keep it open while running), or None if another run has it."""
    return take_lock(LOCK_FILE)


def daily_check_running() -> bool:
    return is_locked(LOCK_FILE)


def take_panel_task_lock() -> IO | None:
    return take_lock(PANEL_TASK_LOCK_FILE)


def panel_task_running() -> bool:
    return is_locked(PANEL_TASK_LOCK_FILE)


def take_lock(path: Path) -> IO | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(path, "a+")
    try:
        _lock(lock_file)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def is_locked(path: Path) -> bool:
    lock_file = take_lock(path)
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
