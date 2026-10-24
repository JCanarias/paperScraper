from abc import ABC, abstractmethod

from models.author import Author
from models.text import Text

class InformationSource(ABC):
    """Source of information, retrieves data."""

    @abstractmethod
    def get_authors(self, query: str) -> list[Author]:
        """Retrieves authors from string input."""

    @abstractmethod
    def get_authors_texts(self, author: Author) -> list[Text]:
        """Returns texts by an author."""

    @abstractmethod
    def get_texts(self, query: str) -> list[Text]:
        """Returns texts from string input."""
        
    @abstractmethod
    def search_by_author(self) -> list[Text]:
        """Returns texts from author search"""