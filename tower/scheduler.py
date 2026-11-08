"""Runs daily_check.py every day at 6:00 (the TZ time zone, Madrid by default).

If the container wasn't running at 6:00 (the tower was off), the check is done as soon as it starts,
once per day. The day of the last check is kept in library/.daily_check.last.
"""
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

RUN_AT = dt.time(6, 0)
LAST_RUN_FILE = Path("library") / ".daily_check.last"
TIME_ZONE = ZoneInfo(os.environ.get("TZ") or "Europe/Madrid")
# Wake up now and then instead of sleeping until 6:00 in one go: a suspended machine or a clock
# change would make a single long sleep end late.
MAX_SLEEP_SECONDS = 600
# Each check is also written here: `docker logs` loses everything when ./update.sh recreates the container.
LOG_FOLDER = Path("library") / ".logs"
LOG_DAYS = 90


def last_run_day() -> dt.date | None:
    try:
        return dt.date.fromisoformat(LAST_RUN_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def run_check(today: dt.date) -> None:
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(LOG_FOLDER / f"daily-{today.isoformat()}.log", "a", encoding="utf-8") as log:
        def show(line: str) -> None:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()

        show(f"{dt.datetime.now(TIME_ZONE):%Y-%m-%d %H:%M} Revisión diaria\n")
        process = subprocess.Popen([sys.executable, "daily_check.py"], cwd=Path(__file__).parent.parent,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            show(line)
        process.wait()
        show(f"{dt.datetime.now(TIME_ZONE):%Y-%m-%d %H:%M} Fin (código {process.returncode})\n")
    remove_old_logs(today)
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(today.isoformat())


def remove_old_logs(today: dt.date) -> None:
    for log_file in LOG_FOLDER.glob("daily-*.log"):
        try:
            day = dt.date.fromisoformat(log_file.stem.removeprefix("daily-"))
        except ValueError:
            continue
        if (today - day).days > LOG_DAYS:
            log_file.unlink()


def main() -> None:
    os.chdir(Path(__file__).parent.parent)
    print(f"Revisión diaria programada a las {RUN_AT:%H:%M} ({TIME_ZONE}).", flush=True)
    while True:
        now = dt.datetime.now(TIME_ZONE)
        if now.time() >= RUN_AT and last_run_day() != now.date():
            run_check(now.date())
            continue
        next_run = dt.datetime.combine(now.date(), RUN_AT, TIME_ZONE)
        if now >= next_run:
            next_run += dt.timedelta(days=1)
        time.sleep(min(MAX_SLEEP_SECONDS, max(1.0, (next_run - now).total_seconds())))


if __name__ == "__main__":
    main()
