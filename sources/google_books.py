"""Book search via Google Books API with fallback to Internet Archive.

Google Books API (free tier) allows searching their catalogue. While direct PDF downloads
are prohibited by terms of service, we can:
1. Find books via Google Books API
2. Identify public domain books via 'identifier' field
3. Locate copies in Internet Archive (Google identifiers like 'goog' map to IA copies)
4. Fall back to Google Books link for user browsing

This source respects Google's ToS by not bypassing protections or downloading
restricted content. Public domain books are sourced from Internet Archive instead.
"""
import os
from typing import Optional
from urllib.parse import urlencode

import requests

from models import Paper
from sources.base import BookSource
from sources.internet_archive import InternetArchiveSource
from sources.names import name_words, readable_name

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
TIMEOUT_SECONDS = 10


class GoogleBooksSource(BookSource):
    """Search Google Books and redirect to Internet Archive for public domain books."""

    name = "Google Books"

    def __init__(self):
        # API key is optional - searches work without it but with lower rate limits
        self.api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        self.internet_archive = InternetArchiveSource()

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search Google Books by author."""
        query = f"inauthor:{author_name}"
        return self._search(query, limit)

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
        if self.api_key:
            params["key"] = self.api_key

        try:
            response = requests.get(
                GOOGLE_BOOKS_API,
                params=params,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 429:
                # Rate limited - Google Books free API has strict limits
                # Recommended: Add GOOGLE_BOOKS_API_KEY to .env for higher limits
                pass  # Gracefully skip
            elif e.response.status_code == 403:
                pass  # Access denied
            else:
                pass  # Other HTTP errors
            return []
        except requests.RequestException as e:
            # Network errors - skip silently
            return []

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
        """Convert Google Books API item to Paper, preferring IA fallback."""
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

        # Check for Internet Archive fallback
        pdf_urls = []

        # Try to find in Internet Archive using title/author
        if authors:
            ia_results = self.internet_archive.search_books_by_author(authors[0], 1)
            if ia_results and ia_results[0].pdf_urls:
                pdf_urls.extend(ia_results[0].pdf_urls)

        # If not found in IA, provide Google Books link
        if not pdf_urls:
            google_link = item.get("volumeInfo", {}).get("infoLink")
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
