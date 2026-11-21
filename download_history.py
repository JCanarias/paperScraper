"""The list of the latest downloads, shown by the web panel (webapp/).

Every work that gets a file (a search, the daily check, a file uploaded by hand) adds a line to
library/.history/downloads.jsonl. The file itself may go to Calibre and leave the folder afterwards;
the line stays.
"""
import datetime as dt
import json
from pathlib import Path

from models import Paper
from storage import LIBRARY_FOLDER

HISTORY_FILE = LIBRARY_FOLDER / ".history" / "downloads.jsonl"
# Older lines are dropped when the file grows past this.
MAX_LINES = 2000


def record(paper: Paper, folder: Path, how: str = "") -> None:
    """Note the download; a failure here never stops a download."""
    line = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "title": paper.title,
        "authors": paper.authors[:3],
        "year": paper.year,
        "source": paper.source or "",
        "folder": folder.name,
        "how": how,
    }
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as history:
            history.write(json.dumps(line, ensure_ascii=False) + "\n")
        if HISTORY_FILE.stat().st_size > MAX_LINES * 400:
            lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()[-MAX_LINES:]
            HISTORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"  Aviso: no se ha podido apuntar la descarga en el historial: {error}")


def latest(count: int) -> list[dict]:
    """The latest downloads, newest first."""
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
        if len(entries) >= count:
            break
    return entries
