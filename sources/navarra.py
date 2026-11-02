"""Articles from Universidad de Navarra journals via OpenAlex.

Universidad de Navarra publishes several open-access philosophy and theology journals:
- Anuario Filosófico
- Scripta Theologica
- Cuadernos de Pensamiento

These journals mark PDFs as open access in OpenAlex with links to their website,
but those links are behind Cloudflare Turnstile. This source:
1. Searches OpenAlex for works by author/title
2. Filters for Universidad de Navarra journals
3. Provides OpenAlex links (which work with modern browsers)
4. Documents the Turnstile challenge for technical approach

For programmatic download, use Selenium with humanized delays and browser
profile to resolve Turnstile. See pdf_finders/selenium_fast.py for example.
"""
import os
from typing import Optional

from sources.openalex import OpenAlexSource
from models import Author, Paper
from sources.base import BookSource

# Known Navarra journal venue IDs in OpenAlex
NAVARRA_VENUES = {
    "V123456",  # Anuario Filosófico (example)
}

# Search filter for Navarra in OpenAlex
NAVARRA_FILTER = 'raw_affiliation:"Universidad de Navarra" OR publisher:"Universidad de Navarra"'


class NavarraBooksSource(BookSource):
    """Access articles from Universidad de Navarra open-access journals via OpenAlex."""

    name = "Universidad de Navarra"

    def __init__(self):
        self.openalex = OpenAlexSource()

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search for articles by author at Navarra universities."""
        # Search OpenAlex for author
        authors = self.openalex.find_authors(author_name)
        if not authors:
            return []

        papers = []
        for author in authors:
            # Get papers by this author
            all_papers = self.openalex.get_papers(author)

            # Filter for Navarra-affiliated papers
            navarra_papers = [
                p for p in all_papers
                if self._is_navarra_paper(p)
            ]
            papers.extend(navarra_papers)

            if len(papers) >= limit:
                break

        return papers[:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search for articles by title at Navarra universities."""
        papers, _ = self.openalex.search_papers_by_title(words, limit)

        # Filter for Navarra-affiliated papers
        navarra_papers = [p for p in papers if self._is_navarra_paper(p)]
        return navarra_papers[:limit]

    @staticmethod
    def _is_navarra_paper(paper: Paper) -> bool:
        """Check if paper is from Universidad de Navarra."""
        if paper.source and "Navarra" in paper.source:
            return True

        # Check journal name for known Navarra journals
        if paper.journal:
            navarra_journals = {
                "Anuario Filosófico",
                "Scripta Theologica",
                "Cuadernos de Pensamiento",
                "Pensamiento",
            }
            return any(j.lower() in paper.journal.lower() for j in navarra_journals)

        return False
