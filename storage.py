import json
from dataclasses import asdict
from pathlib import Path

from models import Author, Paper

PAPERS_FILENAME = "papers.json"


def save_papers(author: Author, papers: list[Paper], folder: Path, profiles: list[Author] | None = None) -> Path:
    """Save an author's list. `profiles` are all the OpenAlex profiles chosen for that person."""
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / PAPERS_FILENAME
    earlier = load_content(file_path) if file_path.exists() else {}

    content = {
        "author": asdict(author),
        "profiles": [asdict(profile) for profile in profiles or [author]],
        # A new search of the same author keeps it followed (or not) by the daily check.
        "follow": earlier.get("follow", False),
        "papers": [asdict(paper) for paper in papers],
    }

    file_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    return file_path


def save_search(words: str, papers: list[Paper], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)

    content = {
        "title_search": words,
        "papers": [asdict(paper) for paper in papers],
    }

    file_path = folder / PAPERS_FILENAME
    file_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    return file_path


def find_saved_lists(library: Path) -> list[Path]:
    return sorted(library.rglob(PAPERS_FILENAME))


def load_papers(file_path: Path) -> list[Paper]:
    content = json.loads(file_path.read_text(encoding="utf-8"))
    return [Paper(**paper) for paper in content["papers"]]


def update_papers(file_path: Path, papers: list[Paper]) -> None:
    # Keep the rest of the file (author or search words) and replace only the papers.
    content = json.loads(file_path.read_text(encoding="utf-8"))
    content["papers"] = [asdict(paper) for paper in papers]
    file_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")


def load_content(file_path: Path) -> dict:
    return json.loads(file_path.read_text(encoding="utf-8"))


def author_profiles(content: dict) -> list[Author]:
    """The OpenAlex profiles of a saved author list; lists saved before only have the main one."""
    return [Author(**profile) for profile in content.get("profiles") or [content["author"]]]


def set_follow(file_path: Path, follow: bool) -> None:
    content = load_content(file_path)
    content["follow"] = follow
    file_path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
