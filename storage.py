import json
from dataclasses import asdict
from pathlib import Path

from models import Author, Paper

PAPERS_FILENAME = "papers.json"


def save_papers(author: Author, papers: list[Paper], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)

    content = {
        "author": asdict(author),
        "papers": [asdict(paper) for paper in papers],
    }

    file_path = folder / PAPERS_FILENAME
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
