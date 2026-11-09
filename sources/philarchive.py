"""Open access philosophy from PhilArchive (philarchive.org), the archive of PhilPapers.

PhilPapers allows harvesting its catalogue through OAI-PMH, but its PDFs are behind a check
for people and its terms forbid fetching them with programs. Many of those works also exist
elsewhere (the journal, arXiv, a university repository...), so we keep a local copy of the
catalogue, search it here and look each work up in OpenAlex, which knows those other copies.
Works without any other copy are left out: they can only be downloaded by hand.

Each lookup is a search in OpenAlex (0.001 $ of the key's daily budget), and the daily check would
repeat the same ones every day, so the answer is kept in the local index for LOOKUP_DAYS days.
"""
import datetime as dt
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict

from duplicates import title_words
from local_index import LocalIndex
from models import Paper
from oai_harvest import dc_values, harvest, readable_name, year_from
from sources.base import BookSource
from sources.names import name_words
from sources.openalex import OpenAlexBudgetSpent, OpenAlexSource

# PhilPapers asks for at least 2 seconds between requests (Crawl-delay); the harvest waits 3.
OAI_URL = "https://philarchive.org/oai.pl"
OPENALEX_CANDIDATES = 5
# After this, a work is looked up again: OpenAlex may know a new copy.
LOOKUP_DAYS = 90


class PhilArchiveSource(BookSource):

    name = "PhilArchive"

    def __init__(self, openalex: OpenAlexSource | None = None):
        self.index = LocalIndex(self.name)
        self.openalex = openalex or OpenAlexSource()

    def _check_index(self) -> None:
        if self.index.count() == 0:
            raise RuntimeError("su catálogo local está vacío; actualízalo desde el menú o con update_indexes.py")

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        self._check_index()
        return self._find_copies(self.index.search_by_author(author_name, limit))

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        self._check_index()
        return self._find_copies(self.index.search_by_title(words, limit))

    def update_index(self, max_minutes: float | None = None) -> bool:
        return harvest(self.index, OAI_URL, parse_record, max_minutes=max_minutes)

    def _find_copies(self, records: list[dict]) -> list[Paper]:
        papers = []
        for record in records:
            paper = self._openalex_copy(record)
            # A DOI is enough: the PDF finders (Unpaywall, Sci-Hub...) look for it later.
            if paper and (paper.pdf_urls or paper.doi):
                paper.identifiers["philarchive"] = record["id"]
                papers.append(paper)
        return papers

    def _openalex_copy(self, record: dict) -> Paper | None:
        surnames = [name_words(author)[-1] for author in record["authors"] if name_words(author)]
        if not surnames or not record["title"]:
            return None
        known, paper = self._known_copy(record["id"])
        if known:
            return paper
        try:
            found = self.openalex.search_by_title_and_author(record["title"], surnames[0], OPENALEX_CANDIDATES)
        except OpenAlexBudgetSpent:
            # Every following lookup would fail too.
            raise
        except Exception:
            return None
        paper = same_title(record["title"], found)
        self._keep_copy(record["id"], paper)
        return paper

    def _known_copy(self, record_id: str) -> tuple[bool, Paper | None]:
        """(True, the copy) when OpenAlex was asked about this record less than LOOKUP_DAYS ago."""
        try:
            kept = json.loads(self.index.get_state(f"openalex:{record_id}") or "null")
            if not kept or dt.date.fromisoformat(kept["date"]) < dt.date.today() - dt.timedelta(days=LOOKUP_DAYS):
                return False, None
            return True, Paper(**kept["paper"]) if kept["paper"] else None
        except (ValueError, KeyError, TypeError):
            return False, None

    def _keep_copy(self, record_id: str, paper: Paper | None) -> None:
        kept = {"date": dt.date.today().isoformat(), "paper": asdict(paper) if paper else None}
        self.index.set_state(f"openalex:{record_id}", json.dumps(kept, ensure_ascii=False))


def same_title(title: str, found: list[Paper]) -> Paper | None:
    wanted = title_words(title)
    for paper in found:
        # The same title, ignoring a subtitle that only one of them has.
        found_words = title_words(paper.title or "")
        if found_words[:len(wanted)] == wanted or wanted[:len(found_words)] == found_words:
            return paper
    return None


def parse_record(dc: ET.Element) -> dict | None:
    titles = dc_values(dc, "title")
    if not titles:
        return None
    return {
        "title": titles[0],
        "authors": [readable_name(name) for name in dc_values(dc, "creator")],
        "year": year_from((dc_values(dc, "date") or [None])[0]),
        "language": (dc_values(dc, "language") or [None])[0],
        "urls": [],
    }
