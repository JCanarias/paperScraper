"""Wikimedia Commons: books scanned by libraries and volunteers (many from Internet Archive and Google),
free to reuse. Only the PDFs are kept: the DjVu files, which are many, can't be saved yet (downloader.py).

The search finds every file that names the author, also books about them, so each file must say in its
"Author" field that it is by them (Commons gives it as "Artist").
"""
import html
import re

import requests

from models import Paper
from sources.base import BookSource
from sources.names import readable_name, same_author

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
TIMEOUT_SECONDS = 60
# Wikimedia asks every program to say who it is and where to find out more (its User-Agent policy).
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
# The search returns files about the author too, so more are asked than kept.
RESULTS_FACTOR = 3
MAX_RESULTS = 100
FILE_NAMESPACE = 6
# "Fichte (IA fichte019655mbp).pdf", "Niebla - IA nieblanivola00unam.pdf": the copy's id, not part of the title.
COPY_ID = re.compile(r"\s*(?:\((?:IA|Google|BHL|HathiTrust)[^)]*\)|-\s*IA\s+\S+)\s*$", re.I)
# "s:fr:Auteur:Johann Gottlieb Fichte": a link to the author's page in Wikisource.
AUTHOR_LINK = re.compile(r"^(?:\w+:)*(?:Auteur|Author|Autor|Autore)\s*:\s*", re.I)
YEAR = re.compile(r"\b(1[4-9]\d\d|20[0-2]\d)\b")


class WikimediaCommonsSource(BookSource):
    name = "Wikimedia Commons"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        books = self._search(f'"{author_name}" filetype:pdf', limit)
        return [book for book in books if any(same_author(author_name, author) for author in book.authors)][:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        return self._search(f"intitle:{words} filetype:pdf", limit)[:limit]

    def _search(self, query: str, limit: int) -> list[Paper]:
        response = requests.get(COMMONS_API_URL, headers=HEADERS, timeout=TIMEOUT_SECONDS, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": FILE_NAMESPACE,
            "gsrsearch": query, "gsrlimit": min(limit * RESULTS_FACTOR, MAX_RESULTS),
            "prop": "imageinfo", "iiprop": "url|mime|extmetadata",
            "iiextmetadatafilter": "Artist|DateTimeOriginal|LicenseShortName",
        })
        response.raise_for_status()
        pages = (response.json().get("query") or {}).get("pages") or {}
        # The search gives them by relevance in "index".
        ordered = sorted(pages.values(), key=lambda page: page.get("index", 0))
        return [book for book in map(self._build_book, ordered) if book]

    def _build_book(self, page: dict) -> Paper | None:
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") != "application/pdf" or not info.get("url"):
            return None
        metadata = info.get("extmetadata") or {}
        artist = plain_text(metadata.get("Artist", {}).get("value", ""))
        title = page["title"].removeprefix("File:").rsplit(".", 1)[0]
        title = COPY_ID.sub("", title).replace("_", " ").strip()
        return Paper(
            title=title,
            year=self._year(plain_text(metadata.get("DateTimeOriginal", {}).get("value", "")), title),
            doi=None,
            # Without the "?utm_source=..." the API adds for its statistics.
            pdf_urls=[info["url"].split("?")[0]],
            authors=[readable_name(name) for name in self._authors(artist)],
            source=self.name,
            identifiers={"commons": str(page.get("pageid", ""))},
        )

    def _authors(self, artist: str) -> list[str]:
        names = [AUTHOR_LINK.sub("", line).strip() for line in re.split(r"\n|;| and | y ", artist)]
        return [name for name in names if name and not name.lower().startswith(("unknown", "desconocido"))]

    def _year(self, date: str, title: str) -> int | None:
        # The date of the work, or the year in the file's name; a date after 1950 is usually the scan's.
        for text in (date, title):
            match = YEAR.search(text)
            if match and int(match.group(1)) <= 1950:
                return int(match.group(1))
        return None


def plain_text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
