"""Reads a bibliography (BibTeX, RIS or plain text, one reference per line) and finds its works.

Each reference is looked for in this order:
1. its DOI, in OpenAlex;
2. its ISBN, in the Internet Archive;
3. its text, in Crossref (which is made for matching references) and then in OpenAlex.
A match is only accepted when almost every word of the found title is in the reference,
so a review of a book ("W. K. C. Guthrie, A History of Greek Philosophy...") isn't taken for the book.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests

from config import UNPAYWALL_EMAIL
from duplicates import title_words
from models import Paper
from sources.internet_archive import InternetArchiveSource
from sources.names import name_words
from sources.openalex import OpenAlexSource

TIMEOUT_SECONDS = 60
CROSSREF_URL = "https://api.crossref.org/works"
# Crossref gives about 100 or more to a right match and about 40-50 to a wrong one.
MIN_CROSSREF_SCORE = 60
# Part of the found title's words that must be in the reference.
MIN_TITLE_WORDS_IN_REFERENCE = 0.8
CANDIDATES = 3
SEARCH_CANDIDATES = 10
MAX_TITLE_GUESSES = 4

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"<>{}]+", re.I)
ISBN_PATTERN = re.compile(r"(?:ISBN(?:-1[03])?:?\s*)?\b((?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx])\b")


@dataclass
class Reference:
    text: str
    doi: str | None = None
    isbn: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)


def read_references(file_path: Path) -> list[Reference]:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if file_path.suffix.lower() == ".bib" or re.search(r"^\s*@\w+\s*\{", text, re.M):
        return parse_bibtex(text)
    if file_path.suffix.lower() == ".ris" or re.search(r"^TY  - ", text, re.M):
        return parse_ris(text)
    return [plain_reference(line.strip()) for line in text.splitlines() if len(line.strip()) > 10]


def parse_bibtex(text: str) -> list[Reference]:
    references = []
    for entry in re.split(r"^\s*@", text, flags=re.M)[1:]:
        fields = {
            name.lower(): re.sub(r"[{}]", "", value).strip()
            for name, value in re.findall(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", entry, re.M | re.S)
        }
        # BibTeX writes "Last, First and Last, First".
        authors = [readable(name) for name in re.split(r"\s+and\s+", fields.get("author", "")) if name.strip()]
        reference = Reference(
            text=" ".join(filter(None, [fields.get("author"), fields.get("title"), fields.get("year")])),
            doi=clean_doi(fields.get("doi")),
            isbn=clean_isbn(fields.get("isbn")),
            title=fields.get("title"),
            authors=authors,
        )
        if reference.text or reference.doi or reference.isbn:
            references.append(reference)
    return references


def parse_ris(text: str) -> list[Reference]:
    references = []
    for record in re.split(r"^ER  -.*$", text, flags=re.M):
        lines = re.findall(r"^([A-Z][A-Z0-9])  - ?(.*)$", record, re.M)
        if not lines:
            continue
        values: dict[str, list[str]] = {}
        for tag, value in lines:
            values.setdefault(tag, []).append(value.strip())
        title = (values.get("TI") or values.get("T1") or values.get("BT") or [None])[0]
        authors = [readable(name) for name in values.get("AU", []) + values.get("A1", [])]
        year = (values.get("PY") or values.get("Y1") or [""])[0][:4]
        references.append(Reference(
            text=" ".join(filter(None, [" ".join(authors), title, year])),
            doi=clean_doi((values.get("DO") or [None])[0]),
            # SN is the ISBN of a book or the ISSN of a journal; clean_isbn drops ISSNs.
            isbn=clean_isbn((values.get("SN") or [None])[0]),
            title=title,
            authors=authors,
        ))
    return references


def plain_reference(line: str) -> Reference:
    doi = DOI_PATTERN.search(line)
    isbn = ISBN_PATTERN.search(line)
    return Reference(
        text=line,
        doi=clean_doi(doi.group(0)) if doi else None,
        isbn=clean_isbn(isbn.group(1)) if isbn else None,
    )


def find_works(references: list[Reference], source: OpenAlexSource,
               archive: InternetArchiveSource) -> tuple[list[Paper], list[Reference]]:
    """Return the works found, and the references that couldn't be found anywhere."""
    found: list[Paper] = []
    missing: list[Reference] = []

    with_doi = [reference for reference in references if reference.doi]
    by_doi = {paper.doi.lower(): paper for paper in source.get_papers_by_dois([r.doi for r in with_doi])}

    for number, reference in enumerate(references, start=1):
        print(f"  [{number}/{len(references)}] {reference.text[:90]}", end=" ", flush=True)
        paper = None
        if reference.doi:
            # A DOI that OpenAlex doesn't know is still useful: the PDF finders look for it.
            paper = by_doi.get(reference.doi.lower()) or Paper(
                title=reference.title or reference.doi, year=None, doi=reference.doi,
                pdf_urls=[], authors=reference.authors,
            )
        if paper is None and reference.isbn:
            paper = first_or_none(safe(lambda: archive.search_books_by_isbn(reference.isbn, 1)))
        if paper is None:
            paper = find_by_text(reference, source, archive)

        if paper is None:
            print("✗")
            missing.append(reference)
        else:
            print("✓")
            found.append(paper)
    return found, missing


def find_by_text(reference: Reference, source: OpenAlexSource, archive: InternetArchiveSource) -> Paper | None:
    query = reference.text
    doi = crossref_doi(query, reference)
    if doi:
        paper = first_or_none(safe(lambda: source.get_papers_by_dois([doi])))
        if paper:
            return paper
    surname = first_surname(reference)
    for title in possible_titles(reference):
        # With the author's surname OpenAlex leaves out the reviews of the work, which repeat its title.
        search = (lambda: source.search_by_title_and_author(title, surname, SEARCH_CANDIDATES)) if surname \
            else (lambda: source.search_works(title, SEARCH_CANDIDATES))
        for paper in safe(search):
            if matches(paper, reference):
                return paper
    # Old books are often only in the libraries of scanned books.
    if reference.title:
        for paper in safe(lambda: archive.search_books_by_title(reference.title, CANDIDATES)):
            if matches(paper, reference):
                return paper
    return None


def crossref_doi(query: str, reference: Reference) -> str | None:
    try:
        response = requests.get(CROSSREF_URL, params={
            "query.bibliographic": query,
            "rows": CANDIDATES,
            "select": "DOI,title,score,author",
            # With an e-mail Crossref puts us in its faster "polite" pool.
            "mailto": UNPAYWALL_EMAIL,
        }, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return None

    for item in response.json()["message"]["items"]:
        if item.get("score", 0) < MIN_CROSSREF_SCORE:
            continue
        candidate = Paper(
            title=(item.get("title") or [""])[0], year=None, doi=item["DOI"], pdf_urls=[],
            authors=[f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])],
        )
        if matches(candidate, reference):
            return item["DOI"]
    return None


def possible_titles(reference: Reference) -> list[str]:
    """The whole reference has too many other words (publisher, city, year) for a search engine,
    so we search the title alone. Without a known title, each part of the reference between
    full stops can be it; the longest ones first.
    """
    if reference.title:
        return [reference.title]
    parts = [part.strip(" ,;") for part in re.split(r"\.\s+|\(\d{4}\w?\)", reference.text)]
    parts = [part for part in parts if len(title_words(part)) >= 2 and not DOI_PATTERN.search(part)]
    parts.sort(key=len, reverse=True)
    return parts[:MAX_TITLE_GUESSES]


def first_surname(reference: Reference) -> str:
    # References usually start with the first author's surname ("Guthrie, W. K. C. ...").
    words = name_words(reference.authors[0])[-1:] if reference.authors else name_words(reference.text)[:1]
    return words[0] if words else ""


def matches(paper: Paper, reference: Reference) -> bool:
    # References often leave out the subtitle ("Orpheus and Greek Religion: A Study of..."),
    # so only the main title must be in the reference.
    found_words = title_words((paper.title or "").split(":")[0])
    reference_words = set(title_words(reference.text))
    if not found_words:
        return False
    in_reference = sum(word in reference_words for word in found_words) / len(found_words)
    if in_reference < MIN_TITLE_WORDS_IN_REFERENCE:
        return False
    # A review repeats the title of the work but has another author, and records without
    # authors are usually the journal's own notes, so an author's surname must be in the reference.
    surnames = {name_words(author)[-1] for author in paper.authors if name_words(author)}
    return bool(surnames & set(name_words(reference.text)))


def readable(name: str) -> str:
    # "Vigo, Alejandro G." -> "Alejandro G. Vigo"
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name.strip()


def clean_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI_PATTERN.search(value)
    # A DOI at the end of a sentence carries its full stop.
    return match.group(0).rstrip(".,;)") if match else None


def clean_isbn(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"[^\dXx]", "", value)
    return digits.upper() if len(digits) in (10, 13) else None


def first_or_none(papers: list[Paper]) -> Paper | None:
    return papers[0] if papers else None


def safe(search) -> list[Paper]:
    # A failing service shouldn't stop the whole bibliography.
    try:
        return search()
    except Exception:
        return []
