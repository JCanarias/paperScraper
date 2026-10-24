from dataclasses import dataclass
from datetime import date

from .author import Author

@dataclass
class Text:
    title: str
    author: Author
    languages: list[str] # ¿ESTOS DEBERÍAN SER IDS?
    translator: Author | None = None# ¿ESTOS DEBERÍAN SER IDS?
    editor: Author | None = None# ¿ESTOS DEBERÍAN SER IDS?
    series: str | None = None
    number: str | None = None
    tags: list[str] | None = None
    isbn: str | None = None
    doi: str | None = None
    issn: str | None = None
    open_alex_id: str | None = None
    downloaded: date | None = None
    published: date | None = None
    publisher: str | None = None