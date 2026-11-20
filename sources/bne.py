"""Public domain books of the Biblioteca Nacional de España (BNE Digital, formerly Biblioteca Digital Hispánica).

The BNE publishes the list of its digitised works in the public domain as open data (datosabiertos.bne.es,
about 100,000 books): a ZIP of CSV files with author, title, date and the link to each work. We download
it once a week (through the browser: bne.es is behind Cloudflare's check), keep the books in the local
index and search them here.
The files are downloaded by hand ("Descargar a mano las pendientes"): when the program asked BNE Digital
for PDFs, its security system blocked the access ("Página de bloqueo"), so it isn't asked again.
"""
import csv
import io
import re
import time
import zipfile
from datetime import datetime, timezone

import browser_session
from languages import language_code
from local_index import LocalIndex, record_to_paper
from models import Paper
from sources.base import BookSource
from sources.names import readable_name

CATALOGUE_URL = "https://www.bne.es/media/datosgob/bdh/dominiopublico/dominiopublico_csv-utf8.zip"
CARD_URL = "https://bnedigital.bne.es/bd/card?oid={id}&site=bdh"
DAYS_BETWEEN_UPDATES = 7
# The list also has engravings, maps, sheet music, manuscripts and recordings.
BOOK_TYPE = "Libro"
# The people of a work come as "Surname, Name , dates -role //"; translators, editors... have a role.
ROLE = re.compile(r"\s-\s*[a-záéíóúñ. ]+$", re.I)


class BNESource(BookSource):

    name = "BNE"
    uses_browser = True

    def __init__(self):
        self.index = LocalIndex(self.name)

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        self._update_if_old()
        return [record_to_paper(record, self.name, "bne") for record in self.index.search_by_author(author_name, limit)]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        self._update_if_old()
        return [record_to_paper(record, self.name, "bne") for record in self.index.search_by_title(words, limit)]

    def update_index(self, max_minutes: float | None = None) -> bool:
        print("  Descargando la lista de obras en dominio público de la BNE...")
        content, _ = browser_session.download(CATALOGUE_URL)
        if not content or not content.startswith(b"PK"):
            raise ValueError("la BNE no ha dado su lista de obras")
        records = []
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in archive.namelist():
                text = archive.read(name).decode("utf-8-sig", "replace")
                records.extend(record for row in csv.DictReader(io.StringIO(text), delimiter=";")
                               if (record := parse_row(row)))
        # The list is the whole collection, so it replaces the old copy.
        self.index.delete_all()
        self.index.save(records)
        self.index.set_state("last_complete", datetime.now(timezone.utc).isoformat())
        return True

    def _update_if_old(self) -> None:
        last = self.index.get_state("last_complete")
        age_days = (time.time() - datetime.fromisoformat(last).timestamp()) / 86400 if last else None
        if age_days is None or age_days > DAYS_BETWEEN_UPDATES:
            try:
                self.update_index()
            except Exception as error:
                # With an old copy we can still search; without any, the BNE is just skipped.
                print(f"  Aviso: no se ha podido actualizar la lista de la BNE ({error})")


def parse_row(row: dict) -> dict | None:
    if row.get("Tipo de documento") != BOOK_TYPE or not row.get("Título"):
        return None
    work_ids = list(dict.fromkeys(re.findall(r"viewer\.vm\?id=(\d+)", row.get("version_digital") or "")))
    if not work_ids:
        return None
    people = [person.strip() for person in (row.get("Autor Personas") or "").split("//") if person.strip()]
    authors = [readable_name(person) for person in people if not ROLE.search(person)]
    year = re.search(r"\d{4}", row.get("Fecha de publicación") or "")
    isbn = re.sub(r"[^\dX]", "", (row.get("ISBN") or "").split("//")[0])
    return {
        "id": row["idBNE"],
        "title": row["Título"].strip(),
        "authors": authors,
        "year": int(year.group()) if year else None,
        "publisher": (row.get("Editorial") or "").split("//")[0].strip() or None,
        "language": language_code(row.get("Lengua de publicación")),
        "isbn": isbn or None,
        "urls": [CARD_URL.format(id=work_id) for work_id in work_ids],
    }


