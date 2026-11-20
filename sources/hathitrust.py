"""Public domain books of HathiTrust that can be read in full from here.

Every request to hathitrust.org (its API included) goes through Cloudflare's check, so the catalogue
search runs in the browser (browser_session.py) and its result page is read.
HathiTrust's terms of use forbid downloading its books with programs (and it blocks them), so the
same edition is downloaded from Internet Archive when it is there (internet_archive_copies.py); the
rest are downloaded by hand ("Descargar a mano las pendientes").
"""
import html
import re
from urllib.parse import urlencode

import browser_session
from models import Paper
from sources.base import BookSource
from sources.names import readable_name, same_author

SEARCH_URL = "https://catalog.hathitrust.org/Search/Home"
READER_URL = "https://babel.hathitrust.org/cgi/pt?id={id}"


class HathiTrustSource(BookSource):

    name = "HathiTrust"
    uses_browser = True

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        papers = self._search(author_name, "author")
        return [paper for paper in papers
                if any(same_author(author_name, author) for author in paper.authors)][:limit]

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        return self._search(words, "title")[:limit]

    def _search(self, words: str, field: str) -> list[Paper]:
        # "ft": only works with some volume in full view (the rest is "search only").
        page = browser_session.get_page(SEARCH_URL + "?" + urlencode({"lookfor": words, "type": field, "ft": "ft"}),
                                        wait_for="record-title")
        articles = re.findall(r'<article class="record.*?</article>', page, re.S)
        return [paper for article in articles if (paper := article_to_paper(article))]


def article_to_paper(article: str) -> Paper | None:
    # A record with several volumes ("Multiple Items") has no single book to download; it's left out.
    full_view = re.search(r'href="//babel\.hathitrust\.org/cgi/pt\?id=([^"]+)"[^>]*>\s*<i[^>]*></i>\s*Full view', article)
    title = re.search(r'<span class="title">(.*?)</span>', article, re.S)
    if not full_view or not title:
        return None
    fields = dict(re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", article, re.S))
    year = re.search(r"\d{4}", fields.get("Published", ""))
    author = html.unescape(fields.get("Author", "")).strip().rstrip(".")
    volume_id = html.unescape(full_view.group(1))
    return Paper(
        title=html.unescape(title.group(1)).strip().split(" / ")[0].rstrip(" ."),
        year=int(year.group()) if year else None, doi=None, pdf_urls=[READER_URL.format(id=volume_id)],
        authors=[readable_name(author)] if author else [], source="HathiTrust",
        identifiers={"hathitrust": volume_id},
    )
