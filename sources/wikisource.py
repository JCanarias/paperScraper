import html
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import requests

from languages import language_allowed
from models import Paper
from sources.base import BookSource
from sources.names import name_words, readable_name, same_author

# Not in config.py yet: the wikis are "https://<language>.wikisource.org" and the EPUBs are made by
# the official Wikisource export tool.
WIKISOURCE_URL = "https://{language}.wikisource.org/w/api.php"
WS_EXPORT_URL = "https://ws-export.wmcloud.org/"
TIMEOUT_SECONDS = 60
# Wikimedia asks every program to say who it is and where to find out more (its User-Agent policy),
# and limits much more the ones that don't.
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
# Wikimedia asks to keep the number of requests at the same time low.
PARALLEL_REQUESTS = 2
MAX_WAIT_SECONDS = 10
# A failed request, an answer that is not JSON, or one without the expected parts.
API_ERRORS = (requests.RequestException, ValueError, KeyError, IndexError)
# Wikis searched, in this order, with the number of their "Author" namespace (it changes between wikis).
AUTHOR_NAMESPACES = {"es": 106, "en": 102, "fr": 102}
# Author pages looked at for each name; the right one is usually the first.
AUTHOR_PAGES = 3
# Many links of an author page are not their works (journals, other authors...), so we check more than we need.
CANDIDATES_FACTOR = 4
TITLE_RESULTS_FACTOR = 3


class WikisourceSource(BookSource):
    """Public domain works transcribed by Wikisource volunteers, downloaded as EPUB.

    Only whole works are returned: a work split into chapters has one page for the whole work
    ("Niebla") and one subpage for each chapter ("Niebla/I"), so pages with "/" in their title are
    left out, and so are disambiguation pages (also used for the list of translations of a work).
    """

    name = "Wikisource"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        books = []
        for language in AUTHOR_NAMESPACES:
            if len(books) >= limit:
                break
            # The wikis of the languages not chosen in "Idiomas" aren't asked (they are the slow part).
            if not language_allowed(language):
                continue
            try:
                books.extend(self._books_by_author(language, author_name, limit - len(books)))
            except API_ERRORS:
                continue
        return books[:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        wanted = set(name_words(words))
        if not wanted:
            return []
        books = []
        for language in AUTHOR_NAMESPACES:
            if len(books) >= limit:
                break
            # The wikis of the languages not chosen in "Idiomas" aren't asked (they are the slow part).
            if not language_allowed(language):
                continue
            try:
                books.extend(self._books_by_title(language, words, limit - len(books)))
            except API_ERRORS:
                continue
        return books[:limit]

    def _books_by_author(self, language: str, author_name: str, limit: int) -> list[Paper]:
        # The works of an author are the pages linked from their author page ("Autor:Miguel de Unamuno").
        # Those links also go to journals, translators... so each work must say it is by the author.
        keep = lambda book: any(same_author(author_name, author) for author in book.authors)
        books = []
        for author_page in self._author_pages(language, author_name):
            titles = self._linked_works(language, author_page)
            books.extend(self._build_books(language, titles, limit - len(books), keep))
            if len(books) >= limit:
                break
        return books

    def _author_pages(self, language: str, author_name: str) -> list[str]:
        namespace = AUTHOR_NAMESPACES[language]
        data = api_get(language, {
            "action": "query",
            "list": "search",
            "srsearch": author_name,
            "srnamespace": namespace,
            "srlimit": AUTHOR_PAGES,
            "srprop": "",
        })
        # Homonyms are dropped: the page name, without "Autor:", must be the author we want.
        titles = [result["title"] for result in data["query"]["search"]]
        return [title for title in titles if same_author(author_name, title.split(":", 1)[-1])]

    def _linked_works(self, language: str, author_page: str) -> list[str]:
        pages = self._linked_pages(language, author_page)
        works = [page["title"] for page in pages if is_whole_work(page)]
        # In the English Wikisource the author page often links to a page listing the translations
        # of a work, marked as disambiguation; the translations themselves are one link further.
        for page in pages:
            if not is_versions_page(page):
                continue
            try:
                translations = self._linked_pages(language, page["title"])
            except API_ERRORS:
                continue
            works.extend(other["title"] for other in translations if is_whole_work(other) and other["title"] not in works)
        return works

    def _linked_pages(self, language: str, title: str) -> list[dict]:
        """The pages linked from a page, in the order they appear in it."""
        # The API gives the links in alphabetical order, but author pages list the main works
        # (novels, essays...) before the short ones (poems, articles), so we keep the page's order.
        data = api_get(language, {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": title,
        })
        text = data["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]

        data = api_get(language, {
            "action": "query",
            "generator": "links",
            "titles": title,
            "gplnamespace": 0,
            "gpllimit": "max",
            "prop": "pageprops",
            "ppprop": "disambiguation",
            "redirects": 1,
        })
        query = data.get("query", {})
        pages = {page["title"]: page for page in query.get("pages", [])}
        # A link can point to a redirect; the API gives the page it leads to.
        redirects = {redirect["from"]: redirect["to"] for redirect in query.get("redirects", [])}

        ordered = []
        for link in re.findall(r"\[\[([^\]|#]+)", text):
            link = " ".join(link.replace("_", " ").split())
            link = redirects.get(link[:1].upper() + link[1:], link[:1].upper() + link[1:])
            if link in pages and pages[link] not in ordered:
                ordered.append(pages[link])
        # Links made by templates are not in the text; they go at the end.
        return ordered + [page for page in pages.values() if page not in ordered]

    def _books_by_title(self, language: str, words: str, limit: int) -> list[Paper]:
        wanted = set(name_words(words))
        # "intitle:" makes the search look only at the page names, not at the whole text.
        query = " ".join(f"intitle:{word}" for word in clean_words(words).split())
        data = api_get(language, {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 0,
            "gsrlimit": limit * TITLE_RESULTS_FACTOR,
            "prop": "pageprops",
            "ppprop": "disambiguation",
            "redirects": 1,
        })
        pages = data.get("query", {}).get("pages", [])
        # The search results come unordered in "pages"; "index" is their place in the results.
        pages.sort(key=lambda page: page.get("index", 0))
        titles = [page["title"] for page in pages if is_whole_work(page) and wanted <= set(name_words(page["title"]))]
        return self._build_books(language, titles, limit, lambda book: True)

    def _build_books(self, language: str, titles: list[str], limit: int, keep: Callable[[Paper], bool]) -> list[Paper]:
        # The details of each work are read in groups, stopping as soon as we have enough.
        books = []
        titles = titles[:limit * CANDIDATES_FACTOR]
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as executor:
            for start in range(0, len(titles), PARALLEL_REQUESTS):
                group = titles[start:start + PARALLEL_REQUESTS]
                found = executor.map(lambda title: self._build_book(language, title), group)
                books.extend(book for book in found if book and keep(book))
                if len(books) >= limit:
                    break
        return books[:limit]

    def _build_book(self, language: str, title: str) -> Paper | None:
        # Every work page has a hidden block ("ws-data") with its title, author, year and publisher;
        # it is what the export tool uses too. It is in the first section, so we don't ask for the whole text.
        try:
            data = api_get(language, {
                "action": "parse",
                "page": title,
                "prop": "text",
                "section": 0,
                "redirects": 1,
            })
            page_html = data["parse"]["text"]
        except API_ERRORS:
            return None

        details = work_details(page_html)
        year = re.search(r"\d{4}", details.get("year", ""))
        page_title = data["parse"].get("title", title)
        return Paper(
            title=best_title(details.get("title", ""), page_title),
            year=int(year.group()) if year else None,
            doi=None,
            pdf_urls=[export_url(language, page_title)],
            authors=split_authors(details.get("author", "")),
            publisher=details.get("publisher") or None,
            language=language,
            source=self.name,
            identifiers={"wikisource": f"{language}:{page_title}"},
        )


def api_get(language: str, params: dict) -> dict:
    for _ in range(2):
        response = requests.get(
            WIKISOURCE_URL.format(language=language),
            params={**params, "format": "json", "formatversion": 2},
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        # With too many requests, Wikimedia says how many seconds to wait; we wait once if it is not long.
        wait = response.headers.get("Retry-After", "")
        if response.status_code != 429 or not wait.isdigit() or int(wait) > MAX_WAIT_SECONDS:
            break
        time.sleep(int(wait))
    response.raise_for_status()
    return response.json()


def is_whole_work(page: dict) -> bool:
    # Missing pages (red links), chapters ("Niebla/I") and disambiguation pages are not whole works.
    return (
        "missing" not in page
        and "invalid" not in page
        and "/" not in page["title"]
        and "disambiguation" not in page.get("pageprops", {})
    )


def is_versions_page(page: dict) -> bool:
    return "missing" not in page and "disambiguation" in page.get("pageprops", {})


def work_details(page_html: str) -> dict[str, str]:
    """Title, author, year... from the hidden "ws-data" block of a work page."""
    block = re.search(r'<div[^>]*id="ws-data".*?</div>', page_html, re.S)
    if not block:
        return {}
    details = {}
    # The Spanish wiki marks each detail with a class ("ws-author"), the English one with an id.
    for match in re.finditer(r'<span[^>]*(?:class|id)="ws-([a-z]+)"[^>]*>(.*?)</span>(?=<span|</div>)', block.group(0), re.S):
        key, value = match.groups()
        # A title can have a second line with the original title; we keep the first one.
        value = re.split(r"<br\s*/?>", value)[0]
        value = html.unescape(re.sub(r"<[^>]+>", "", value))
        details.setdefault(key, " ".join(value.split()))
    return details


def best_title(work_title: str, page_title: str) -> str:
    """The full title of the work, or the page name when the full title is not reliable."""
    # Page names can end with a note to tell apart works with the same name ("Castilla (Unamuno)").
    short_title = re.sub(r"\s*\([^)]*\)$", "", page_title)
    # The full title ("Abel Sánchez, una historia de pasión") is better if it contains the page name;
    # sometimes it is the name of the first chapter ("Índice") or is written in capitals.
    if work_title and not work_title.isupper() and set(name_words(short_title)) <= set(name_words(work_title)):
        return work_title
    return short_title


def split_authors(text: str) -> list[str]:
    # The author can come as a link to the author page ("Autor:Miguel de Unamuno"), and there can be several.
    names = re.split(r"\s*(?:,|;|&| y | and | et )\s*", text)
    names = [name.split(":", 1)[-1].strip() for name in names]
    return [readable_name(name) for name in names if name and name.lower() not in ("anónimo", "anonymous", "anonyme")]


def export_url(language: str, page_title: str) -> str:
    return f"{WS_EXPORT_URL}?{urlencode({'format': 'epub-3', 'lang': language, 'page': page_title})}"


def clean_words(words: str) -> str:
    # Characters with a special meaning in the search syntax are removed.
    return re.sub(r'[():"\[\]{}^~*?\\!-]', " ", words)
