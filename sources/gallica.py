"""Public domain books of Gallica, the digital library of the Bibliothèque nationale de France.

Its catalogue can be searched with SRU, but every request to gallica.bnf.fr goes through
Cloudflare's check, so the search runs in the browser (browser_session.py).
Gallica refuses to make PDFs for programs (Cloudflare blocks them outright, it isn't a check to
pass), so the PDF is made from the images of the book's pages, given by its IIIF API (gallica_pages.py).
"""
import html
import re
from urllib.parse import urlencode

import browser_session
from languages import language_code
from models import Paper
from sources.base import BookSource
from sources.names import readable_name, same_author

SRU_URL = "https://gallica.bnf.fr/SRU"
MAX_RECORDS = 50
# Printed books; Gallica also has manuscripts, maps, images, sound recordings and periodicals.
BOOK_TYPE = "monographie imprimée"


class GallicaSource(BookSource):

    name = "Gallica"
    uses_browser = True

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        surname = author_name.split()[-1] if author_name.split() else ""
        if not surname:
            return []
        papers = self._search(f'dc.creator all "{clean(surname)}"')
        return [paper for paper in papers
                if any(same_author(author_name, author) for author in paper.authors)][:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        return self._search(f'dc.title all "{clean(words)}"')[:limit]

    def _search(self, query: str) -> list[Paper]:
        address = SRU_URL + "?" + urlencode({
            "operation": "searchRetrieve", "version": "1.2", "maximumRecords": MAX_RECORDS,
            "query": f'{query} and dc.type all "monographie"',
        })
        answer = browser_session.get_page(address)
        records = re.findall(r"<oai_dc:dc[^>]*>(.*?)</oai_dc:dc>", answer, re.S)
        return [paper for record in records if (paper := record_to_paper(record))]


def clean(text: str) -> str:
    return re.sub(r'["\\]', " ", text).strip()


def values(record: str, tag: str) -> list[str]:
    return [html.unescape(value).strip() for value in re.findall(rf"<dc:{tag}>(.*?)</dc:{tag}>", record, re.S)]


def record_to_paper(record: str) -> Paper | None:
    if "domaine public" not in values(record, "rights") or BOOK_TYPE not in values(record, "type"):
        return None
    address = next((value for value in values(record, "identifier") if "/ark:/" in value), None)
    titles = values(record, "title")
    if not address or not titles:
        return None
    # "Unamuno, Miguel de (1864-1936). Auteur du texte": the author's name, without dates and role.
    authors = [readable_name(re.sub(r"\s*\(.*$", "", creator)) for creator in values(record, "creator")
               if "auteur du texte" in creator.lower()]
    year = next((int(match.group()) for value in values(record, "date") if (match := re.search(r"\d{4}", value))), None)
    return Paper(
        title=titles[0].split(" / ")[0].replace(" : ", ": "), year=year, doi=None, pdf_urls=[address],
        authors=authors, language=language_code(next(iter(values(record, "language")), None)),
        publisher=next(iter(values(record, "publisher")), None), source="Gallica",
        identifiers={"gallica": address.rsplit("/", 1)[-1]},
    )
