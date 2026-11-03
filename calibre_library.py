"""The user's Calibre library, through its content server (calibre-server).

The server has a JSON API (the one its web interface uses):
- /ajax/library-info gives the libraries and the default one;
- /ajax/search/<library>?query=...&num=... gives the ids of the books that match;
- /ajax/books/<library>?ids=1,2,3 gives their details (title, authors, identifiers...);
- /cdb/add-book/<job>/<add duplicates y|n>/<file name>/<library> adds a book (the file is the body);
- /cdb/set-fields/<book>/<library> changes its details.
Adding books needs a user that is not read-only.
"""
import os
from pathlib import Path
from urllib.parse import quote

import requests
from requests.auth import AuthBase, HTTPBasicAuth, HTTPDigestAuth

from duplicates import title_words
from models import Paper
from sources.names import surnames

TIMEOUT_SECONDS = 60
UPLOAD_TIMEOUT_SECONDS = 300
BOOKS_PER_REQUEST = 500
# The whole library; the server needs a number.
ALL_BOOKS = 1_000_000
# The ISSN is the journal's, not the work's, and "url" can be anything, so they don't identify a work.
NOT_WORK_IDENTIFIERS = ("issn", "url")
# Every book we add gets this tag, so they can be found in Calibre ("tags:paperScraper").
DEFAULT_TAG = "paperScraper"
# Fields whose values are shared by many books (see _existing_case).
SHARED_FIELDS = ("tags", "series", "publisher")


class CalibreLibrary:

    def __init__(self, url: str, username: str, password: str, library_id: str = "", tag: str = DEFAULT_TAG):
        self.url = url.rstrip("/")
        self.tag = tag
        self.session = requests.Session()
        self.session.auth = self._choose_auth(username, password)
        self.library_id = library_id or self._get("/ajax/library-info")["default_library"]
        # Identifiers ("doi:10.1038/...") and "title words|author surname" of every book in the library.
        self.identifiers: set[str] = set()
        self.titles: set[str] = set()
        # The books added in this run: the only ones whose details we may change.
        self.added_ids: set[int] = set()
        # Existing values of the shared fields, by lowercase ("nature" -> "Nature"); filled when needed.
        self.existing_names: dict[str, dict[str, str]] = {}

    @classmethod
    def from_environment(cls) -> "CalibreLibrary | None":
        """The library set in .env, or None when there is none or it can't be reached."""
        url = os.environ.get("CALIBRE_URL", "").strip()
        if not url:
            return None
        try:
            return cls(
                url,
                os.environ.get("CALIBRE_USERNAME", ""),
                os.environ.get("CALIBRE_PASSWORD", ""),
                os.environ.get("CALIBRE_LIBRARY", "").strip(),
                os.environ.get("CALIBRE_TAG", "").strip() or DEFAULT_TAG,
            )
        except Exception as error:
            print(f"Aviso: no se puede conectar con Calibre ({url}): {error}")
            return None

    def load_index(self) -> int:
        """Read the title, authors and identifiers of every book; return how many there are."""
        book_ids = self._get(f"/ajax/search/{self.library_id}", {"query": "", "num": ALL_BOOKS})["book_ids"]
        self.identifiers.clear()
        self.titles.clear()
        for start in range(0, len(book_ids), BOOKS_PER_REQUEST):
            ids = ",".join(str(book_id) for book_id in book_ids[start:start + BOOKS_PER_REQUEST])
            books = self._get(f"/ajax/books/{self.library_id}", {"ids": ids})
            for book in books.values():
                if book:
                    self._add_to_index(book["title"], book["authors"], book["identifiers"])
        return len(book_ids)

    def mark_papers(self, papers: list[Paper]) -> int:
        """Set `in_calibre` on the works the library already has; return how many."""
        for paper in papers:
            paper.in_calibre = self.contains(paper)
        return sum(paper.in_calibre for paper in papers)

    def contains(self, paper: Paper) -> bool:
        if any(key in self.identifiers for key in identifier_keys(paper.all_identifiers())):
            return True
        return any(key in self.titles for key in title_keys(paper.title, paper.authors))

    def upload(self, file_path: Path, paper: Paper) -> bool:
        """Add the file to the library; return False when Calibre says it is already there."""
        result = self.add_file(file_path)
        if result.get("duplicates"):
            return False

        # Calibre reads most details from the file, but not the series, and it moves the date
        # to the day before in some time zones, so we set them again.
        self._set_fields(result["book_id"], book_fields(paper))
        self._add_to_index(paper.title, paper.authors, paper.all_identifiers())
        paper.in_calibre = True
        return True

    def add_file(self, file_path: Path, allow_duplicates: bool = False) -> dict:
        """Add a book file with the details Calibre reads from it, plus our tag.

        The answer has "book_id", "title" and "authors", or "duplicates" (the books with the same title, whatever
        their authors) when the book was already there and wasn't added.
        """
        duplicates = "y" if allow_duplicates else "n"
        response = self.session.post(
            f"{self.url}/cdb/add-book/0/{duplicates}/{quote(file_path.name)}/{self.library_id}",
            data=file_path.read_bytes(),
            timeout=UPLOAD_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("duplicates"):
            self.added_ids.add(result["book_id"])
            # Only our tag: the ones that come inside the files are usually noise.
            self._set_fields(result["book_id"], {"tags": [self.tag]})
            self._add_to_index(result.get("title", ""), result.get("authors", []), {})
        return result

    def _set_fields(self, book_id: int, changes: dict) -> None:
        # The books that were already in the library are never changed.
        if book_id not in self.added_ids:
            raise RuntimeError(f"El libro {book_id} no se ha añadido ahora; no se toca.")
        changes = {field: self._existing_case(field, value) for field, value in changes.items()}
        response = self.session.post(
            f"{self.url}/cdb/set-fields/{book_id}/{self.library_id}",
            json={"changes": changes, "loaded_book_ids": [book_id]},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    def _existing_case(self, field: str, value):
        """Write a tag, series or publisher the way the library already has it.

        Tags, series and publishers are shared by many books. When the new value differs from an
        existing one only in capitals ("nature" / "Nature"), the server renames the existing one
        in every book, so we use the existing spelling.
        """
        if field not in SHARED_FIELDS:
            return value
        if field not in self.existing_names:
            names = self._get(f"/interface-data/field-names/{field}", {"library_id": self.library_id})
            self.existing_names[field] = {name.lower(): name for name in names}
        known = self.existing_names[field]
        values = value if isinstance(value, list) else [value]
        fixed = [known.setdefault(item.lower(), item) for item in values]
        return fixed if isinstance(value, list) else fixed[0]

    def _add_to_index(self, title: str, authors: list[str], identifiers: dict[str, str]) -> None:
        self.identifiers.update(identifier_keys(identifiers))
        self.titles.update(title_keys(title, authors))

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self.session.get(f"{self.url}{path}", params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def _choose_auth(self, username: str, password: str) -> AuthBase:
        # The server asks for "Digest" or "Basic" depending on how it was set up.
        response = requests.get(f"{self.url}/ajax/library-info", timeout=TIMEOUT_SECONDS)
        if response.headers.get("WWW-Authenticate", "").lower().startswith("basic"):
            return HTTPBasicAuth(username, password)
        return HTTPDigestAuth(username, password)


def identifier_keys(identifiers: dict[str, str]) -> set[str]:
    return {
        f"{scheme.lower()}:{value.strip().lower()}"
        for scheme, value in identifiers.items()
        if value and scheme.lower() not in NOT_WORK_IDENTIFIERS
    }


def title_keys(title: str | None, authors: list[str]) -> set[str]:
    # The same work can have a different capitalisation, accents or punctuation in each place,
    # so we compare the words of the title and the surname of each author.
    words = " ".join(title_words(title or ""))
    if not words:
        return set()
    every_surname = {word for author in authors for word in surnames(author)}
    return {f"{words}|{surname}" for surname in every_surname}


def book_fields(paper: Paper) -> dict:
    fields = {"identifiers": paper.all_identifiers()}
    if paper.journal:
        fields["series"] = paper.journal
        try:
            fields["series_index"] = float(paper.volume)
        except (TypeError, ValueError):
            fields["series_index"] = 1.0
    date = paper.best_date()
    if date:
        fields["pubdate"] = date
    if paper.publisher:
        fields["publisher"] = paper.publisher
    return fields
