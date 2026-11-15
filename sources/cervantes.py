"""Works of the Biblioteca Virtual Miguel de Cervantes (cervantesvirtual.com), with their PDF.

Its catalogue is open as linked data (BVMC Labs, CC0), with a SPARQL endpoint that programs may use.
In it, a person is the author of works; each work has editions ("manifestations") and these have
copies ("items"); the PDF ones give the address of the file (/descargaPdf/...).
The PDFs are behind Cloudflare's check, so the downloader gets them with the browser (browser_session.py).
"""
import re
import time

import requests

from models import Paper
from sources.base import BookSource
from sources.names import readable_name, same_author

SPARQL_URL = "https://data.cervantesvirtual.com/bvmc-lod/repositories/data"
HEADERS = {
    "User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)",
    "Accept": "application/sparql-results+json",
}
TIMEOUT_SECONDS = 90
SECONDS_BETWEEN_QUERIES = 2
PREFIXES = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdac: <http://rdaregistry.info/Elements/c/>
PREFIX rdaw: <http://rdaregistry.info/Elements/w/>
PREFIX rdam: <http://rdaregistry.info/Elements/m/>
PREFIX rdai: <http://rdaregistry.info/Elements/i/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
"""
# The works with a PDF copy, and their title, date, language and authors.
WORKS_WITH_PDF = """
  ?work rdaw:titleOfTheWork ?title ; rdaw:manifestationOfWork ?edition .
  ?edition rdam:exemplarOfManifestation ?copy .
  ?copy rdai:identifierForTheItem ?file ; rdai:itemSpecificCarrierCharacteristic "pdf" .
  OPTIONAL { ?edition rdam:dateOfPublication ?date }
  OPTIONAL { ?edition dc:language ?language }
  OPTIONAL { ?work rdaw:author ?author . ?author rdfs:label ?author_name }
"""


class CervantesSource(BookSource):

    name = "Cervantes"

    def __init__(self):
        self.last_query = 0.0

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        surname = sparql_text(author_name.split()[-1].lower()) if author_name.split() else ""
        if not surname:
            return []
        rows = self._query(f"""{PREFIXES}
            SELECT ?work ?title ?date ?language ?file ?author_name WHERE {{
              ?person a rdac:Person ; rdfs:label ?person_name .
              FILTER(CONTAINS(LCASE(?person_name), "{surname}"))
              ?work rdaw:author ?person .
              {WORKS_WITH_PDF}
            }} LIMIT {limit * 20}""")
        papers = rows_to_papers(rows)
        return [paper for paper in papers
                if any(same_author(author_name, author) for author in paper.authors)][:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        title_words = [sparql_text(word.lower()) for word in words.split() if len(word) > 2]
        if not title_words:
            return []
        filters = " ".join(f'FILTER(CONTAINS(LCASE(?title), "{word}"))' for word in title_words)
        rows = self._query(f"""{PREFIXES}
            SELECT ?work ?title ?date ?language ?file ?author_name WHERE {{
              {WORKS_WITH_PDF}
              {filters}
            }} LIMIT {limit * 5}""")
        return rows_to_papers(rows)[:limit]

    def _query(self, query: str) -> list[dict]:
        wait = self.last_query + SECONDS_BETWEEN_QUERIES - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        response = requests.get(SPARQL_URL, params={"query": query}, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        self.last_query = time.monotonic()
        response.raise_for_status()
        return [{name: value["value"] for name, value in row.items()}
                for row in response.json()["results"]["bindings"]]


def sparql_text(text: str) -> str:
    # The words go inside a quoted SPARQL string.
    return re.sub(r'["\\\n\r]', "", text).strip()


def rows_to_papers(rows: list[dict]) -> list[Paper]:
    # A work comes in one row per author and per PDF copy.
    papers: dict[str, Paper] = {}
    for row in rows:
        work_id = row["work"].rsplit("/", 1)[-1]
        paper = papers.get(work_id)
        if paper is None:
            year = re.search(r"(\d{4})$", row.get("date", ""))
            language = row.get("language", "").rsplit("/", 1)[-1] or None
            paper = papers[work_id] = Paper(
                title=row["title"].strip(), year=int(year.group(1)) if year else None, doi=None,
                pdf_urls=[], language=language, source="Cervantes", identifiers={"bvmc": work_id},
            )
        if row["file"] not in paper.pdf_urls:
            paper.pdf_urls.append(row["file"])
        author = readable_name(row["author_name"]) if row.get("author_name") else None
        if author and author not in paper.authors:
            paper.authors.append(author)
    return list(papers.values())
