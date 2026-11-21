"""Book search via Google Books API with fallback to Internet Archive.

Google Books API (free tier) allows searching their catalogue. While direct PDF downloads
are prohibited by terms of service, we can:
1. Find books via Google Books API
2. Identify public domain books via 'identifier' field
3. Keep the Google Books link, for the user to look at (it is not a file)

A copy in Internet Archive used to be looked for by the first author's name alone, which gave the
file of any other book of that author: it is no longer done (Internet Archive is searched by itself).

This source respects Google's ToS by not bypassing protections or downloading
restricted content. Public domain books are sourced from Internet Archive instead: the copy of
the same Google scan, when it is there (internet_archive_copies.py).
"""
import os
from typing import Optional

import requests

from models import Paper
from sources.base import BookSource
from sources.names import readable_name, same_author

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
TIMEOUT_SECONDS = 10


class GoogleBooksSource(BookSource):
    """Search Google Books and redirect to Internet Archive for public domain books."""

    name = "Google Books"

    def __init__(self):
        # Without a key every request shares one daily quota with everyone else in the world, which
        # is always spent ("429 Quota exceeded"): with no key the source is not used (work_search.py).
        self.api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        self.available = bool(self.api_key)

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search Google Books by author."""
        query = f"inauthor:{author_name}"
        # Google matches loosely (one word of the name is enough): the other people are left out.
        return [paper for paper in self._search(query, limit)
                if any(same_author(author_name, author) for author in paper.authors)]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search Google Books by title."""
        return self._search(words, limit)

    def _search(self, query: str, limit: int) -> list[Paper]:
        """Execute Google Books API search."""
        params = {
            "q": query,
            "maxResults": min(limit, 40),
            "printType": "books",
        }
        params["key"] = self.api_key
        # Errors are not hidden: the search loop skips a library that fails for the rest of the run.
        response = requests.get(GOOGLE_BOOKS_API, params=params, timeout=TIMEOUT_SECONDS, headers=HEADERS)
        response.raise_for_status()

        try:
            data = response.json()
            items = data.get("items", [])
        except (ValueError, KeyError):
            return []

        papers = []
        for item in items[:limit]:
            try:
                paper = self._item_to_paper(item)
                if paper:
                    papers.append(paper)
            except Exception:
                continue

        return papers

    def _item_to_paper(self, item: dict) -> Optional[Paper]:
        """Convert Google Books API item to Paper."""
        volume_info = item.get("volumeInfo", {})
        title = volume_info.get("title")
        if not title:
            return None

        authors = volume_info.get("authors", [])
        published_date = volume_info.get("publishedDate", "")
        year = None
        if published_date:
            try:
                year = int(published_date.split("-")[0])
            except (ValueError, IndexError):
                pass

        # The Google Books page: not a file, but it lets the user see the book when asked about it.
        pdf_urls = []
        google_link = volume_info.get("infoLink")
        if google_link:
            pdf_urls.append(google_link)

        return Paper(
            title=title,
            authors=[readable_name(a) for a in authors],
            year=year,
            doi=None,
            journal=volume_info.get("publisher"),
            pdf_urls=pdf_urls,
            source="Google Books",
        )
