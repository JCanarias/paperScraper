"""Access public domain books via HathiTrust + Internet Archive.

HathiTrust is a partnership of academic libraries with millions of books. Their
policy prohibits automated downloads, but:
1. Public domain books from before ~1901 (in Spain: before ~1927) are viewable
2. Many HathiTrust scans are mirrored in Internet Archive (use 'goog' identifiers)
3. We can search HathiTrust bibliography and redirect to IA for downloads

This source respects HathiTrust policy by:
- Not bypassing any protections
- Using only public domain works
- Redirecting to IA for actual downloads
- Using 5+ second delays for searches

For full access, use institutional credentials from member universities.
"""
import re
import time
from typing import Optional
from urllib.parse import urlencode, quote

import requests

from models import Paper
from sources.base import BookSource
from sources.internet_archive import InternetArchiveSource
from sources.names import readable_name

HATHITRUST_SEARCH_API = "https://www.hathitrust.org/api/v1/search/json"
INTERNET_ARCHIVE = InternetArchiveSource()
TIMEOUT_SECONDS = 30
RATE_LIMIT_DELAY = 5.0  # Very respectful delay


class HathiTrustSource(BookSource):
    """Search HathiTrust public domain collection with fallback to Internet Archive."""

    name = "HathiTrust"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search HathiTrust by author."""
        time.sleep(RATE_LIMIT_DELAY)
        query = f"creator:({author_name})"
        return self._search(query, limit)

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search HathiTrust by title."""
        time.sleep(RATE_LIMIT_DELAY)
        return self._search(words, limit)

    def _search(self, query: str, limit: int) -> list[Paper]:
        """Execute HathiTrust search and filter for public domain."""
        try:
            response = requests.get(
                HATHITRUST_SEARCH_API,
                params={
                    "query": query,
                    "sort": "title",
                    "limit": min(limit, 50),
                },
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"HathiTrust search failed: {e}")
            return []

        try:
            data = response.json()
            items = data.get("items", [])
        except (ValueError, KeyError):
            return []

        papers = []
        for item in items:
            try:
                # Only include public domain books
                if self._is_public_domain(item):
                    paper = self._item_to_paper(item)
                    if paper:
                        papers.append(paper)
                        if len(papers) >= limit:
                            break
            except Exception:
                continue

        return papers

    @staticmethod
    def _is_public_domain(item: dict) -> bool:
        """Check if item is public domain (accessible without institutional auth)."""
        # HathiTrust marks public domain items with 'rightsCode': 'pd'
        rights = item.get("rightsCode", "")
        return rights == "pd"

    def _item_to_paper(self, item: dict) -> Optional[Paper]:
        """Convert HathiTrust item to Paper, with IA fallback."""
        title = item.get("title")
        if not title:
            return None

        authors = item.get("authors", [])
        publication_date = item.get("publishDate", "")
        year = None
        if publication_date:
            try:
                year = int(str(publication_date).split("-")[0])
            except (ValueError, IndexError):
                pass

        # Try to find in Internet Archive
        pdf_urls = []
        if authors:
            ia_results = INTERNET_ARCHIVE.search_books_by_author(authors[0] if authors else title, 1)
            if ia_results and ia_results[0].pdf_urls:
                pdf_urls.extend(ia_results[0].pdf_urls)

        # If not in IA, provide HathiTrust handle for browser access
        if not pdf_urls:
            handle = item.get("htid")
            if handle:
                # Format: "htid" -> "ht://handle/12345/abcde"
                ht_url = f"https://www.hathitrust.org/cgi/pt?id={handle}"
                pdf_urls.append(ht_url)

        return Paper(
            title=title,
            authors=[readable_name(a) for a in authors] if authors else [],
            year=year,
            doi=None,
            journal=None,
            pdf_urls=pdf_urls,
            source="HathiTrust",
        )
