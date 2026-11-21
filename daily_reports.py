"""The reports of the daily checks, shown by the web panel (webapp/), as the one sent by Telegram.

Every check, also a failed one, adds a line to library/.history/daily_reports.jsonl when it ends.
"""
import json

from storage import LIBRARY_FOLDER

REPORTS_FILE = LIBRARY_FOLDER / ".history" / "daily_reports.jsonl"
# About three months of checks.
MAX_REPORTS = 90


def save(report: dict) -> None:
    """Keep the report; a failure here never stops the check."""
    try:
        REPORTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = REPORTS_FILE.read_text(encoding="utf-8").splitlines() if REPORTS_FILE.exists() else []
        lines = lines[-(MAX_REPORTS - 1):] + [json.dumps(report, ensure_ascii=False)]
        REPORTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"Aviso: no se ha podido guardar el informe para el panel: {error}")


def latest(count: int) -> list[dict]:
    """The latest reports, newest first."""
    try:
        lines = REPORTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    reports = []
    for line in reversed(lines):
        try:
            reports.append(json.loads(line))
        except ValueError:
            continue
        if len(reports) >= count:
            break
    return reports
