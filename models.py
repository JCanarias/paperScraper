from dataclasses import dataclass, field


@dataclass
class Author:
    id: str
    name: str
    works_count: int
    institutions: list[str]


@dataclass
class Paper:
    title: str
    year: int | None
    doi: str | None
    pdf_urls: list[str]
    downloaded: bool = False
    authors: list[str] = field(default_factory=list)
    # Extra details that are written into the PDF so Calibre can read them.
    publication_date: str | None = None
    journal: str | None = None
    volume: str | None = None
    publisher: str | None = None
    language: str | None = None
    isbn: str | None = None
    # Where the work was found ("Gutenberg", "Internet Archive"...), shown when choosing books.
    source: str | None = None

    def best_date(self) -> str | None:
        # With only a year, Calibre fills the month and day with today's; January 1st is less misleading.
        if self.publication_date:
            return self.publication_date
        if self.year:
            return f"{self.year}-01-01"
        return None
