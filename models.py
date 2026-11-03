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
    # Other identifiers ("openalex", "pmid", "issn", "gutenberg"...); Calibre keeps them all.
    identifiers: dict[str, str] = field(default_factory=dict)
    # Where the work was found ("Gutenberg", "Internet Archive"...), shown when choosing books.
    source: str | None = None
    # Added to the file name when another work in the same list would get the same one.
    filename_tag: str | None = None
    # The user chose to download it; the ones still without a file can be retried later.
    wanted: bool = False
    # Already in the user's Calibre library (checked at every search).
    in_calibre: bool = False
    # Its file was sent to Calibre and Calibre confirmed it has it, so the local copy was deleted.
    # It stays "in Calibre" even if Calibre's record changes later, so it is never downloaded again.
    sent_to_calibre: bool = False

    def all_identifiers(self) -> dict[str, str]:
        """DOI, ISBN and the other ids of the work, with the lowercase scheme names Calibre uses."""
        identifiers = {"doi": self.doi, "isbn": self.isbn, **self.identifiers}
        return {scheme.lower(): value for scheme, value in identifiers.items() if value}

    def best_date(self) -> str | None:
        # With only a year, Calibre fills the month and day with today's; January 1st is less misleading.
        if self.publication_date:
            return self.publication_date
        if self.year:
            return f"{self.year}-01-01"
        return None
