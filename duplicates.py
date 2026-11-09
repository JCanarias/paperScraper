"""Joins the copies of the same work found in several places (OpenAlex, Dialnet, Internet Archive...).

A work is often in OpenAlex twice (the arXiv preprint and the published article) and also in
other libraries. We keep one record, preferring the published version, and add to it the links
and identifiers of the others, so every place where the file might be is tried.
"""
import re
import unicodedata
from difflib import SequenceMatcher

from models import Paper
from sources.names import surnames

# DOI prefixes of preprint servers: arXiv, Zenodo, SSRN, OSF (and its PsyArXiv, SocArXiv...), bioRxiv.
PREPRINT_DOI_PREFIXES = ("10.48550/", "10.5281/", "10.2139/", "10.31219/", "10.31234/", "10.31235/", "10.1101/")
# Titles at least this long are rarely shared by two different works of the same author.
MIN_WORDS_FOR_SAME_TITLE = 4
# From this length, two titles count as the same with 90 % of their words in common and in order.
MIN_WORDS_FOR_SIMILAR_TITLE = 6
MIN_TITLE_SIMILARITY = 0.9
PREPRINT_JOURNAL_WORDS = ("arxiv", "zenodo", "ssrn", "preprint", "rxiv", "repository", "repositorio")


def merge_duplicates(papers: list[Paper]) -> list[Paper]:
    """Return the works with each repeated one merged into a single record, keeping the order."""
    merged: list[Paper] = []
    for paper in papers:
        twin = next((kept for kept in merged if same_work(kept, paper)), None)
        if twin is None:
            merged.append(paper)
            continue
        best, other = (paper, twin) if better_record(paper, twin) else (twin, paper)
        combine(best, other)
        merged[merged.index(twin)] = best
    return merged


def same_work(one: Paper, other: Paper) -> bool:
    if republished(one, other):
        return True
    if one.doi and other.doi:
        if one.doi.lower() == other.doi.lower():
            return True
        # Two different DOIs of published works are two different works ("Presentación" of two issues).
        if not is_preprint(one) and not is_preprint(other):
            return False
    if not one.title or not other.title or title_words(one.title) != title_words(other.title):
        return False
    if not shared_surname(one.authors, other.authors):
        return False
    # The same title in two languages are two different books (translations).
    if one.language and other.language and one.language[:2].lower() != other.language[:2].lower():
        return False
    # A preprint is usually from the same year as the article, or one or two years before.
    if one.year and other.year and abs(one.year - other.year) > 2:
        return False
    return True


def republished(one: Paper, other: Paper) -> bool:
    """The same work recorded twice by its journal, with two DOIs and two years.

    Some journals gave new DOIs to their old issues (Anuario Filosófico in 2018), and OpenAlex
    keeps both records. A long title, the same author and the same journal (or an unknown one)
    are enough to tell; short titles like "Presentación" repeat in every issue, so they don't count.
    """
    words = title_words(one.title or "")
    other_words = title_words(other.title or "")
    if len(words) < MIN_WORDS_FOR_SAME_TITLE or not similar_titles(words, other_words):
        return False
    if not shared_surname(one.authors, other.authors):
        return False
    if one.journal and other.journal and title_words(one.journal) != title_words(other.journal):
        return False
    return True


def similar_titles(words: list[str], other_words: list[str]) -> bool:
    # Long titles are written with small differences in each catalogue (an article,
    # quotes, a dropped word): "la solución de Kant al amor..." / "solución de Kant al amor...".
    if words == other_words:
        return True
    if min(len(words), len(other_words)) < MIN_WORDS_FOR_SIMILAR_TITLE:
        return False
    return SequenceMatcher(None, words, other_words).ratio() >= MIN_TITLE_SIMILARITY


def is_preprint(paper: Paper) -> bool:
    doi = (paper.doi or "").lower()
    journal = (paper.journal or "").lower()
    return doi.startswith(PREPRINT_DOI_PREFIXES) or any(word in journal for word in PREPRINT_JOURNAL_WORDS)


def better_record(one: Paper, other: Paper) -> bool:
    """Whether `one` describes the work better than `other`: published, with DOI, more details."""
    def score(paper: Paper) -> tuple:
        details = sum(bool(value) for value in (paper.journal, paper.publisher, paper.publication_date, paper.isbn))
        return (not is_preprint(paper), bool(paper.doi), paper.source is None, details)
    return score(one) > score(other)


def combine(best: Paper, other: Paper) -> None:
    # The best record's own links go first; the others' are tried after them.
    best.pdf_urls.extend(url for url in other.pdf_urls if url not in best.pdf_urls)
    for scheme, value in other.identifiers.items():
        best.identifiers.setdefault(scheme, value)
    # The preprint's DOI (an arXiv one, say) still helps to find its file and in Calibre.
    if other.doi and other.doi.lower() != (best.doi or "").lower():
        best.identifiers.setdefault("preprint_doi", other.doi)
    for field in ("year", "publication_date", "journal", "volume", "publisher", "language", "isbn"):
        if not getattr(best, field) and getattr(other, field):
            setattr(best, field, getattr(other, field))
    if not best.authors:
        best.authors = other.authors
    best.wanted = best.wanted or other.wanted
    best.in_calibre = best.in_calibre or other.in_calibre
    best.sent_to_calibre = best.sent_to_calibre or other.sent_to_calibre
    # Where each copy came from (OpenAlex records have no source): a doubtful source backed by
    # a reliable one is no longer doubtful (reviews.py).
    for place in (other.source or "OpenAlex", *other.also_found_in):
        if place != (best.source or "OpenAlex") and place not in best.also_found_in:
            best.also_found_in.append(place)


def shared_surname(authors: list[str], other_authors: list[str]) -> bool:
    own = {word for author in authors for word in surnames(author)}
    other = {word for author in other_authors for word in surnames(author)}
    # Without authors on either side we can't tell; the title alone isn't enough.
    return bool(own & other)


def title_words(title: str) -> list[str]:
    # Unlike names, numbers matter in titles: "Presentación 48-3" is not "Presentación".
    without_accents = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", without_accents.lower())
