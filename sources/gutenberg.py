from collections.abc import Callable

import requests

from config import GUTENDEX_API_URL
from models import Paper
from sources.base import BookSource
from sources.names import name_words, readable_name, same_author

TIMEOUT_SECONDS = 60
# Gutendex gives 32 books per page; a common surname can match hundreds of them.
MAX_PAGES = 5
EPUB = "application/epub+zip"
PDF = "application/pdf"


class GutenbergSource(BookSource):
    """Public domain classics from Project Gutenberg, searched through Gutendex."""

    name = "Gutenberg"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        # Gutendex looks for the words in the title and in the author, and OpenAlex names often
        # have only initials, so we search the surname and keep the books whose author matches.
        words = name_words(author_name)
        if not words:
            return []
        return self._search(words[-1], limit, lambda book: any(
            same_author(author_name, author) for author in book.authors
        ))

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        wanted = set(name_words(words))
        return self._search(words, limit, lambda book: wanted <= set(name_words(book.title)))

    def _search(self, words: str, limit: int, keep: Callable[[Paper], bool]) -> list[Paper]:
        books = []
        url = f"{GUTENDEX_API_URL}/books/"
        params = {"search": words}

        # Gutendex returns results in pages; "next" is the link to the following one.
        for _ in range(MAX_PAGES):
            if not url or len(books) >= limit:
                break
            response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            found = (self._build_book(result) for result in data["results"])
            books.extend(book for book in found if book.pdf_urls and keep(book))
            url = data["next"]
            params = None

        return books[:limit]

    def _build_book(self, result: dict) -> Paper:
        formats = result["formats"]
        urls = [formats[file_type] for file_type in (EPUB, PDF) if file_type in formats]
        return Paper(
            title=result["title"],
            # Gutenberg doesn't say when the book was first published.
            year=None,
            doi=None,
            pdf_urls=urls,
            authors=[readable_name(author["name"]) for author in result["authors"]],
            language=(result["languages"] or [None])[0],
            source=self.name,
        )
