"""What a long task is doing, as numbers that the web panel draws (webapp/), besides its log.

Only when PAPERSCRAPER_PROGRESS names a file: the panel's tasks and the daily check set it. In the menu
nothing is written. The file is rewritten whole at each change (a few times a minute at most), so the
panel always reads a complete one. A failure here never stops a task.
"""
import datetime as dt
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

ENVIRONMENT_VARIABLE = "PAPERSCRAPER_PROGRESS"
# The latest works shown by the panel.
EVENTS_KEPT = 40
# The finders' class names, as the panel shows them.
FINDER_NAMES = {
    "UnpaywallFinder": "Unpaywall", "SemanticScholarFinder": "Semantic Scholar", "CoreFinder": "CORE",
    "SeleniumSciHubFinder": "Sci-Hub", "CustomLegalSourceFinder": "otras webs",
}

_state: dict | None = None


def _path() -> Path | None:
    value = os.environ.get(ENVIRONMENT_VARIABLE)
    return Path(value) if value else None


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _get() -> dict | None:
    global _state
    if _path() is None:
        return None
    if _state is None:
        _state = {"started": _now(), "group": None, "groups_done": 0, "groups_total": None, "step": None,
                  "detail": None, "current": None, "total": 0, "downloaded": 0, "not_found": 0,
                  "uploaded": 0, "upload_failed": 0, "by_source": {}, "events": [], "updated": _now()}
    return _state


def _save() -> None:
    path = _path()
    if path is None or _state is None:
        return
    _state["updated"] = _now()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass


def _event(kind: str, title: str, note: str = "") -> None:
    state = _get()
    state["events"].append({"time": _now()[11:16], "kind": kind, "title": title, "note": note})
    del state["events"][:-EVENTS_KEPT]


def groups(total: int) -> None:
    """How many lists (authors) the task goes through."""
    state = _get()
    if state is None:
        return
    state["groups_total"] = total
    _save()


def group(name: str) -> None:
    """A new list (an author, a search) starts."""
    state = _get()
    if state is None:
        return
    if state["group"] is not None:
        state["groups_done"] += 1
    state.update(group=name, step=None, detail=None, current=None)
    _save()


def step(text: str) -> None:
    """What the task is doing now (searching in OpenAlex, asking Unpaywall, uploading to Calibre…)."""
    state = _get()
    if state is None:
        return
    state.update(step=text, detail=None, current=None)
    _save()


def finder_step(finder) -> None:
    name = type(finder).__name__
    step(f"Buscando enlaces en {FINDER_NAMES.get(name, name.removesuffix('Finder'))}")


def detail(text: str) -> None:
    """How a long piece goes (the pages of a book that is put together)."""
    state = _get()
    if state is None:
        return
    state["detail"] = text
    _save()


def works(count: int) -> None:
    """Works added to the ones the task looks a file for."""
    state = _get()
    if state is None or not count:
        return
    state["total"] += count
    _save()


def trying(title: str) -> None:
    state = _get()
    if state is None:
        return
    state.update(current={"title": title, "since": _now()}, detail=None)
    _save()


def downloaded(title: str, url: str) -> None:
    state = _get()
    if state is None:
        return
    source = (urlparse(url).hostname or "?").removeprefix("www.")
    state["downloaded"] += 1
    state["by_source"][source] = state["by_source"].get(source, 0) + 1
    state["current"] = None
    _event("ok", title, source)
    _save()


def not_found(titles: list[str]) -> None:
    """The works that ended the search without a file."""
    state = _get()
    if state is None or not titles:
        return
    state["not_found"] += len(titles)
    state["current"] = None
    for title in titles:
        _event("bad", title, "sin archivo")
    _save()


def uploaded(title: str, ok: bool, note: str = "") -> None:
    state = _get()
    if state is None:
        return
    state["uploaded" if ok else "upload_failed"] += 1
    _event("up" if ok else "bad", title, note or ("subida a Calibre" if ok else "no se ha podido subir"))
    _save()


def read(path: Path) -> dict | None:
    """The progress written by a task (for the panel)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
