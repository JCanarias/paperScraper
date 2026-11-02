"""Local copies of the catalogues of libraries that can't be searched directly (Dialnet, PhilArchive, DOAB).

Those libraries let programs download their whole catalogue (an OAI-PMH harvest or a daily file),
but not search it, so we keep a copy in a SQLite file and search it here.
Each record keeps what we need to build a Paper: title, authors, year, links...
"""
import json
import os
import sqlite3
from pathlib import Path

from duplicates import title_words
from models import Paper
from sources.names import name_words, same_author

DATABASE_PATH = Path(os.environ.get("INDEX_DATABASE", "") or Path(__file__).parent / "data" / "indexes.sqlite")
FIELDS = ("title", "authors", "year", "publisher", "journal", "volume", "language", "isbn", "doi", "urls")
# A common surname can match thousands of records; the author check runs on these.
MAX_AUTHOR_CANDIDATES = 5000


class LocalIndex:

    def __init__(self, source: str):
        self.source = source
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Two harvests can write at the same time; each waits for the other instead of failing.
        self.database = sqlite3.connect(DATABASE_PATH, timeout=120)
        self.database.executescript("""
            CREATE TABLE IF NOT EXISTS works (
                source TEXT, id TEXT, title TEXT, title_words TEXT, authors TEXT, author_words TEXT,
                year INTEGER, publisher TEXT, journal TEXT, volume TEXT, language TEXT,
                isbn TEXT, doi TEXT, urls TEXT,
                PRIMARY KEY (source, id)
            );
            CREATE TABLE IF NOT EXISTS state (source TEXT, key TEXT, value TEXT, PRIMARY KEY (source, key));
        """)

    def save(self, records: list[dict]) -> None:
        """Add or replace records; each one is a dict with "id" and some of FIELDS."""
        rows = []
        for record in records:
            authors = record.get("authors") or []
            rows.append((
                self.source, record["id"], record.get("title"),
                # Spaces around the words let us search whole words with LIKE '% word %'.
                f" {' '.join(title_words(record.get('title') or ''))} ",
                json.dumps(authors, ensure_ascii=False),
                f" {' '.join(word for author in authors for word in name_words(author))} ",
                record.get("year"), record.get("publisher"), record.get("journal"), record.get("volume"),
                record.get("language"), record.get("isbn"), record.get("doi"),
                json.dumps(record.get("urls") or []),
            ))
        with self.database:
            self.database.executemany(
                "INSERT OR REPLACE INTO works VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
            )

    def delete(self, ids: list[str]) -> None:
        with self.database:
            self.database.executemany(
                "DELETE FROM works WHERE source = ? AND id = ?", [(self.source, work_id) for work_id in ids],
            )

    def delete_all(self) -> None:
        with self.database:
            self.database.execute("DELETE FROM works WHERE source = ?", (self.source,))

    def count(self) -> int:
        return self.database.execute("SELECT COUNT(*) FROM works WHERE source = ?", (self.source,)).fetchone()[0]

    def get_state(self, key: str) -> str | None:
        row = self.database.execute(
            "SELECT value FROM state WHERE source = ? AND key = ?", (self.source, key),
        ).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str | None) -> None:
        with self.database:
            self.database.execute(
                "INSERT OR REPLACE INTO state VALUES (?, ?, ?)", (self.source, key, value),
            )

    def search_by_title(self, words: str, limit: int) -> list[dict]:
        wanted = title_words(words)
        if not wanted:
            return []
        conditions = " AND ".join("title_words LIKE ?" for _ in wanted)
        rows = self.database.execute(
            f"SELECT * FROM works WHERE source = ? AND {conditions} LIMIT ?",
            (self.source, *[f"% {word} %" for word in wanted], limit),
        )
        return [self._record(row) for row in rows]

    def search_by_author(self, author_name: str, limit: int) -> list[dict]:
        words = name_words(author_name)
        if not words:
            return []
        # The surname narrows the search; same_author then drops the homonyms.
        rows = self.database.execute(
            "SELECT * FROM works WHERE source = ? AND author_words LIKE ? LIMIT ?",
            (self.source, f"% {words[-1]} %", MAX_AUTHOR_CANDIDATES),
        )
        records = []
        for row in rows:
            record = self._record(row)
            if any(same_author(author_name, author) for author in record["authors"]):
                records.append(record)
                if len(records) >= limit:
                    break
        return records

    def _record(self, row: tuple) -> dict:
        columns = ("source", "id", "title", "title_words", "authors", "author_words", *FIELDS[2:])
        record = dict(zip(columns, row))
        record["authors"] = json.loads(record["authors"])
        record["urls"] = json.loads(record["urls"])
        return record


def record_to_paper(record: dict, source: str, identifier_scheme: str) -> Paper:
    return Paper(
        title=record["title"],
        year=record["year"],
        doi=record["doi"],
        pdf_urls=list(record["urls"]),
        authors=record["authors"],
        journal=record["journal"],
        volume=record["volume"],
        publisher=record["publisher"],
        language=record["language"],
        isbn=record["isbn"],
        source=source,
        identifiers={identifier_scheme: record["id"]},
    )
