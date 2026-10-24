import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import requests

from config import INTERNET_ARCHIVE_URL
from models import Paper
from sources.base import BookSource
from sources.names import name_words, readable_name, same_author

TIMEOUT_SECONDS = 60
PARALLEL_REQUESTS = 5
AUTHOR_RESULTS_FACTOR = 4
# Books in these collections can only be borrowed, not downloaded.
LENDING_COLLECTIONS = ("inlibrary", "printdisabled", "lendinglibrary")
FIELDS = ("identifier", "title", "creator", "date", "language", "publisher", "isbn")
# Preferred formats first: a PDF keeps the original pages; the EPUBs made from scans have many OCR errors.
FORMATS = ("Text PDF", "Additional Text PDF", "Image Container PDF", "EPUB")


class InternetArchiveSource(BookSource):
    """Freely downloadable books (mostly public domain) from the Internet Archive."""

    name = "Internet Archive"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        # OpenAlex names often have only initials, so we search the surname and keep the books
        # whose author matches. Many results are dropped, so we ask for more than we need.
        words = name_words(author_name)
        if not words:
            return []
        return self._search(f"creator:({words[-1]})", limit * AUTHOR_RESULTS_FACTOR, limit, lambda item: any(
            same_author(author_name, creator) for creator in creators(item)
        ))

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        return self._search(f"title:({clean_words(words)})", limit, limit, lambda item: True)

    def _search(self, query: str, rows: int, limit: int, keep: Callable[[dict], bool]) -> list[Paper]:
        excluded = " AND ".join(f"-collection:{collection}" for collection in LENDING_COLLECTIONS)
        response = requests.get(f"{INTERNET_ARCHIVE_URL}/advancedsearch.php", params={
            "q": f"{query} AND mediatype:texts AND {excluded} AND -access-restricted-item:true",
            "fl[]": FIELDS,
            "rows": rows,
            "output": "json",
        }, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        items = [item for item in response.json()["response"]["docs"] if keep(item)][:limit]

        # The file names change from one book to another, so we ask for each book's list of files.
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as executor:
            file_urls = list(executor.map(self._find_file_urls, [item["identifier"] for item in items]))

        return [self._build_book(item, urls) for item, urls in zip(items, file_urls) if urls]

    def _find_file_urls(self, identifier: str) -> list[str]:
        try:
            response = requests.get(f"{INTERNET_ARCHIVE_URL}/metadata/{identifier}", timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            return []

        files = response.json().get("files", [])
        urls = []
        for wanted_format in FORMATS:
            for file in files:
                if file.get("format") == wanted_format:
                    urls.append(f"{INTERNET_ARCHIVE_URL}/download/{identifier}/{file['name']}")
        return urls

    def _build_book(self, item: dict, urls: list[str]) -> Paper:
        year = first(item.get("date"), "")[:4]
        return Paper(
            title=first(item.get("title"), "(sin título)"),
            year=int(year) if year.isdigit() else None,
            doi=None,
            pdf_urls=urls,
            authors=creators(item),
            publisher=first(item.get("publisher"), None),
            language=first(item.get("language"), None),
            isbn=clean_isbn(first(item.get("isbn"), None)),
            source=self.name,
        )


def clean_words(words: str) -> str:
    # Characters with a special meaning in the search syntax are removed.
    return re.sub(r'[():"\[\]{}^~*?\\]', " ", words)


def creators(item: dict) -> list[str]:
    # Several authors can come in one value, separated by ";" ("Jaffrey, Jess; Brown, Horace").
    names = [name for value in as_list(item.get("creator")) for name in value.split(";")]
    return [readable_name(name) for name in names if name.strip()]


def as_list(value: str | list | None) -> list:
    # The Internet Archive gives a single value as a string and several as a list.
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def first(value: str | list | None, default: str | None) -> str | None:
    values = as_list(value)
    return values[0] if values else default


def clean_isbn(isbn: str | None) -> str | None:
    if not isbn:
        return None
    isbn = re.sub(r"[^0-9Xx]", "", isbn).upper()
    return isbn if len(isbn) in (10, 13) else None
