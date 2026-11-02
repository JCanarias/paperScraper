"""Open access academic books from DOAB (Directory of Open Access Books) and OAPEN.

DOAB's search API only answers to allowed addresses, but every day it publishes its whole
catalogue as a free file (CC0) with the download link of each book. We download that file
once a week, keep it in the local index and search it here.
Many books are hosted by OAPEN, which is often overloaded; the Internet Archive keeps a copy
of most of them (collection "oapen-library"), so that copy is tried first.
"""
import csv
import io
import re
import time
from datetime import datetime, timezone

import requests

from local_index import LocalIndex, record_to_paper
from models import Paper
from oai_harvest import readable_name
from sources.base import BookSource

CATALOGUE_URL = "https://memo.doabooks.org/file/oapen/DOAB_KBART_books_with_download_url.tsv"
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
TIMEOUT_SECONDS = 300
DAYS_BETWEEN_UPDATES = 7
# Their terms forbid downloading with programs; their books can be read on their websites.
EXCLUDED_HOSTS = ("jstor.org", "muse.jhu.edu")
OAPEN_BITSTREAM = re.compile(r"library\.oapen\.org/bitstream/(20\.500\.12657)/(\d+)/\d+/([^/?#]+)$")
ARCHIVE_COPY = "https://archive.org/download/oapen-{prefix}-{number}/{file}"


class DoabSource(BookSource):

    name = "DOAB"

    def __init__(self):
        self.index = LocalIndex(self.name)

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        self._update_if_old()
        return [self._paper(record) for record in self.index.search_by_author(author_name, limit)]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        self._update_if_old()
        return [self._paper(record) for record in self.index.search_by_title(words, limit)]

    def update_index(self, max_minutes: float | None = None) -> bool:
        print("  Descargando el catálogo de DOAB...")
        response = requests.get(CATALOGUE_URL, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        # KBART is plain tab-separated text: quotes inside a title are just quotes.
        rows = csv.DictReader(io.StringIO(response.content.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE)
        records = [record for row in rows if (record := parse_row(row))]
        # The file is the whole catalogue, so it replaces the old copy (books can be withdrawn).
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
                # With an old copy we can still search; without any, DOAB is just skipped.
                print(f"  Aviso: no se ha podido actualizar el catálogo de DOAB ({error})")

    def _paper(self, record: dict) -> Paper:
        paper = record_to_paper(record, self.name, "doab")
        paper.identifiers = {"doab": record["id"]}
        return paper


def parse_row(row: dict) -> dict | None:
    urls = []
    for url in (row.get("title_url") or "").split("||"):
        url = url.strip()
        if not url or any(host in url for host in EXCLUDED_HOSTS):
            continue
        copy = OAPEN_BITSTREAM.search(url)
        if copy:
            urls.append(ARCHIVE_COPY.format(prefix=copy.group(1), number=copy.group(2), file=copy.group(3)))
        urls.append(url)
    if not urls or not row.get("publication_title"):
        return None

    # KBART gives only the first author; edited volumes have an editor instead.
    person = row.get("first_author") or row.get("first_editor") or ""
    year = (row.get("date_monograph_published_print") or row.get("date_monograph_published_online") or "")[:4]
    return {
        "id": row.get("title_id") or urls[-1],
        "title": row["publication_title"].replace(" : ", ": "),
        "authors": [readable_name(person)] if person else [],
        "year": int(year) if year.isdigit() else None,
        "publisher": row.get("publisher_name") or None,
        "isbn": re.sub(r"[^\dX]", "", row.get("print_identifier") or row.get("online_identifier") or "") or None,
        "doi": row.get("doi_identifier") or None,
        "urls": list(dict.fromkeys(urls)),
    }
