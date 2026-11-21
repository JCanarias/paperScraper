"""Texts of European libraries through Europeana's search API (EUROPEANA_API_KEY in .env, free).

Europeana gathers the catalogues of many libraries (Hispana, Memoria Digital de Catalunya, MDZ,
Polona...). Most records only link to the work's page in its library; the downloader looks for the
file there (citation_pdf_url). Only works free to reuse (public domain, Creative Commons) are kept.
"""
import os
import re

import requests

from languages import language_code
from models import Paper
from sources.base import BookSource
from sources.names import readable_name, same_author

SEARCH_URL = "https://api.europeana.eu/record/v2/search.json"
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
TIMEOUT_SECONDS = 30
MAX_ROWS = 100
# The rights statements that allow keeping a copy; "In Copyright" ones are left out.
FREE_RIGHTS = ("publicdomain", "creativecommons.org/licenses", "rightsstatements.org/vocab/NoC")
# These libraries have their own source (sources/bne.py, sources/cervantes.py), which gives the file.
OWN_SOURCE_PROVIDERS = ("National Library of Spain", "Foundation Virtual Library Miguel de Cervantes")


class EuropeanaSource(BookSource):

    name = "Europeana"

    def __init__(self):
        self.api_key = os.getenv("EUROPEANA_API_KEY")
        self.available = bool(self.api_key)

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        surname = author_name.split()[-1] if author_name.split() else ""
        if not surname:
            return []
        papers = self._search(f'who:("{clean(surname)}")', limit * 3)
        return [paper for paper in papers
                if any(same_author(author_name, author) for author in paper.authors)][:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        return self._search(f'title:({clean(words)})', limit)

    def _search(self, query: str, rows: int) -> list[Paper]:
        # The key goes in "wskey": with any other name Europeana answers "Invalid API key".
        response = requests.get(SEARCH_URL, params={
            "wskey": self.api_key, "query": query, "qf": ["TYPE:TEXT"],
            "rows": min(rows, MAX_ROWS), "profile": "rich",
        }, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return [paper for record in response.json().get("items", []) if (paper := record_to_paper(record))]


def clean(text: str) -> str:
    return re.sub(r'["()\\:]', " ", text).strip()


def record_to_paper(record: dict) -> Paper | None:
    rights = " ".join(record.get("rights") or [])
    provider = (record.get("dataProvider") or [""])[0]
    if not any(free in rights for free in FREE_RIGHTS) or provider in OWN_SOURCE_PROVIDERS:
        return None
    title = (record.get("title") or [""])[0].strip()
    urls = [*(record.get("edmIsShownBy") or []), *(record.get("edmIsShownAt") or [])]
    if not title or not urls:
        return None
    # The creators come as names and as links to Europeana's own record of each person.
    authors = list(dict.fromkeys(readable_name(name) for name in record.get("dcCreator") or []
                                 if not name.startswith("http")))
    year = next((int(match.group()) for value in record.get("year") or []
                 if (match := re.search(r"\d{4}", value))), None)
    return Paper(
        title=title, year=year, doi=None, pdf_urls=list(dict.fromkeys(urls)), authors=authors,
        language=language_code((record.get("language") or [None])[0]), publisher=provider or None,
        source="Europeana", identifiers={"europeana": record.get("id", "").strip("/")},
    )
