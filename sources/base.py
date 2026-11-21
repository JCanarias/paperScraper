from abc import ABC, abstractmethod

from models import Author, Paper


class Source(ABC):
    """Common interface that every paper source must implement."""

    @abstractmethod
    def find_authors(self, name: str) -> list[Author]:
        """Return the authors whose name matches the given one."""

    @abstractmethod
    def get_papers(self, author: Author) -> list[Paper]:
        """Return all the papers written by the given author."""

    @abstractmethod
    def search_papers_by_title(self, words: str, limit: int) -> tuple[list[Paper], int]:
        """Return up to `limit` papers whose title contains the given words, and the total number of matches."""


class BookSource(ABC):
    """Common interface for the places where we look for whole books."""

    name: str
    # It goes through the shared Chrome (browser_session.py): the ones that do are searched one after
    # another, while the rest are searched at the same time (work_search.find_books).
    uses_browser: bool = False

    @abstractmethod
    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Return up to `limit` books written by the given author."""

    @abstractmethod
    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Return up to `limit` books whose title contains the given words."""
