from datetime import date

from dataclasses import dataclass

@dataclass
class Author:
    name: str
    surnames: list[str] | None
    birth_date: date | None
    death_date: date | None
    birth_place: str | None
    death_place: str | None
    
    # Ids.
    open_alex_id: str | None
    orcid: str | None
    