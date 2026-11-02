"""Books and texts from European digital libraries through Europeana's API.

Europeana aggregates millions of items from libraries, museums, and archives across Europe.
Requires a free API key from europeana.eu (register at: https://pro.europeana.eu/page/apis).
"""
import os
from typing import Optional

import requests

from models import Paper
from sources.base import BookSource
from sources.names import name_words, readable_name, same_author

EUROPEANA_API_URL = "https://api.europeana.eu/record/v2/search.json"
TIMEOUT_SECONDS = 30
PARALLEL_REQUESTS = 2


class EuropeanaSource(BookSource):
    """Search for books and texts in European digital libraries via Europeana."""

    name = "Europeana"

    def __init__(self):
        self.api_key = os.getenv("EUROPEANA_API_KEY")
        self.available = bool(self.api_key)

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search for books by author in Europeana."""
        if not self.available:
            return []
        words = name_words(author_name)
        if not words:
            return []

        # Search with creator field and filter by type (books/texts)
        query = f'creator:"{author_name}" OR creator:{words[-1]}'
        return self._search(query, limit)

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search for books by title in Europeana."""
        if not self.available:
            return []
        return self._search(f'title:{words} OR text:"{words}"', limit)

    def _search(self, query: str, limit: int) -> list[Paper]:
        """Execute search and return papers."""
        try:
            response = requests.get(
                EUROPEANA_API_URL,
                params={
                    "query": query,
                    "apikey": self.api_key,
                    "rows": min(limit, 100),
                    "profile": "rich",
                    "qf": 'TYPE:("TEXT" OR "IMAGE")',
                },
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                # Invalid or missing API key - skip silently
                pass
            else:
                pass
            return []
        except requests.RequestException:
            # Network errors - skip silently
            return []

        try:
            data = response.json()
            items = data.get("items", [])
        except (ValueError, KeyError):
            print("Europeana returned invalid JSON")
            return []

        papers = []
        for item in items[:limit]:
            try:
                paper = self._item_to_paper(item)
                if paper:
                    papers.append(paper)
            except Exception as e:
                print(f"Error converting Europeana item: {e}")
                continue

        return papers

    def _item_to_paper(self, item: dict) -> Optional[Paper]:
        """Convert a Europeana API item to a Paper object."""
        title = item.get("title", [None])[0] if isinstance(item.get("title"), list) else item.get("title")
        if not title:
            return None

        # Extract authors/creators
        creators = item.get("dcCreator", [])
        if isinstance(creators, str):
            creators = [creators]
        authors = [readable_name(c) for c in creators] if creators else []

        # Get year
        dates = item.get("dctermsIssued", [])
        year = None
        if dates:
            try:
                year = int(str(dates[0]).split("-")[0])
            except (ValueError, IndexError):
                pass

        # Get language
        languages = item.get("language", [])
        language = languages[0] if languages else None

        # Build download links from EDM isShownAt and isShownBy
        pdf_urls = []
        if item.get("edmIsShownBy"):
            pdf_urls.append(item["edmIsShownBy"])
        if item.get("edmIsShownAt"):
            pdf_urls.append(item["edmIsShownAt"])

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=item.get("dcIdentifier", [""])[0] if item.get("dcIdentifier") else None,
            journal=None,
            pdf_urls=pdf_urls,
            source="Europeana",
        )
