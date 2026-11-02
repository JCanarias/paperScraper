"""Articles of Spanish-language journals with their full text in Dialnet (dialnet.unirioja.es).

Dialnet doesn't let programs use its search pages (robots.txt), but it offers its whole catalogue
through OAI-PMH, and its rights statement allows "making a copy for your own personal purposes".
So we keep a local copy of the Humanities part (OAI set 21, which includes Philosophy), search it
here, and download the PDF of each chosen article from /descarga/, a path robots.txt allows.
"""
import re
import xml.etree.ElementTree as ET

from local_index import LocalIndex, record_to_paper
from models import Paper
from oai_harvest import dc_values, harvest, readable_name, year_from
from sources.base import BookSource

DIALNET_URL = "https://dialnet.unirioja.es"
OAI_URL = f"{DIALNET_URL}/oai/OAIHandler"
# 21 = Humanidades (Philosophy, History, Arts...). Others: 20 Psicología y educación, 23 Filologías.
HARVESTED_SETS = ("21",)
# Dialnet gives three-letter language codes; Calibre and the rest of the program use two letters.
LANGUAGES = {"spa": "es", "eng": "en", "por": "pt", "fre": "fr", "fra": "fr", "ita": "it",
             "ger": "de", "deu": "de", "cat": "ca", "glg": "gl", "baq": "eu", "eus": "eu", "lat": "la"}


class DialnetSource(BookSource):

    name = "Dialnet"

    def __init__(self):
        self.index = LocalIndex(self.name)

    def _check_index(self) -> None:
        if self.index.count() == 0:
            raise RuntimeError("su catálogo local está vacío; actualízalo desde el menú o con update_indexes.py")

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        self._check_index()
        return [self._paper(record) for record in self.index.search_by_author(author_name, limit)]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        self._check_index()
        return [self._paper(record) for record in self.index.search_by_title(words, limit)]

    def update_index(self, max_minutes: float | None = None) -> bool:
        complete = True
        for set_name in HARVESTED_SETS:
            complete = harvest(self.index, OAI_URL, parse_record, set_name, max_minutes) and complete
        return complete

    def _paper(self, record: dict) -> Paper:
        paper = record_to_paper(record, self.name, "dialnet")
        # The article's number in Dialnet (the one in its links), not the OAI record's id.
        code = re.search(r"/(\d+)\.pdf$", record["urls"][0]) if record["urls"] else None
        paper.identifiers = {"dialnet": code.group(1)} if code else {}
        return paper


def parse_record(dc: ET.Element) -> dict | None:
    code = next((re.search(r"codigo=(\d+)", value).group(1)
                 for value in dc_values(dc, "identifier") if "codigo=" in value), None)
    titles = dc_values(dc, "title")
    if not code or not titles:
        return None
    # "Sancho el sabio: Revista de cultura..., ISSN 1131-5350, Nº 10, 1999, pags. 163-200"
    source = (dc_values(dc, "source") or [""])[0]
    journal = source.split(", ISSN")[0].strip() or None
    volume = re.search(r"(?:Vol\.|Nº)\s*([\w-]+)", source)
    language = (dc_values(dc, "language") or [None])[0]
    return {
        "title": titles[0],
        "authors": [readable_name(name) for name in dc_values(dc, "creator")],
        "year": year_from((dc_values(dc, "date") or [None])[0]),
        "publisher": (dc_values(dc, "publisher") or [None])[0],
        "journal": journal,
        "volume": volume.group(1) if volume else None,
        "language": LANGUAGES.get(language, language),
        "urls": [f"{DIALNET_URL}/descarga/articulo/{code}.pdf"],
    }
