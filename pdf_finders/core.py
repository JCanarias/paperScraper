import re
import time
import unicodedata

import requests

from config import CORE_API_KEY, CORE_API_URL
from models import Paper
from pdf_finders.base import PdfFinder

# CORE collects the full texts of thousands of university repositories.
# It searches by title, so it also works for papers without a DOI.
TITLES_PER_REQUEST = 10
RESULTS_PER_REQUEST = 100
TIMEOUT_SECONDS = 60
TOO_MANY_REQUESTS = 429
MAX_ATTEMPTS = 5
DEFAULT_WAIT_SECONDS = 10
# Very short titles ("Introduction", "Reply") match too many unrelated works.
MIN_TITLE_WORDS = 3


class CoreFinder(PdfFinder):

    def find_pdf_urls(self, papers: list[Paper]) -> dict[int, list[str]]:
        positions = {}
        for position, paper in enumerate(papers):
            title = normalize(paper.title)
            if len(title.split()) >= MIN_TITLE_WORDS:
                positions.setdefault(title, []).append(position)
        if not positions:
            return {}

        print(f"[CORE] Buscando {len(positions)} títulos...")
        pdf_urls = {}
        titles = list(positions)
        for start in range(0, len(titles), TITLES_PER_REQUEST):
            for result in self._search(titles[start:start + TITLES_PER_REQUEST]):
                for position in positions.get(normalize(result["title"] or ""), []):
                    if self._is_same_paper(papers[position], result):
                        urls = pdf_urls.setdefault(position, [])
                        if result["downloadUrl"] not in urls:
                            urls.append(result["downloadUrl"])
        print(f"[CORE] ✓ {len(pdf_urls)}/{len(papers)} con PDF")
        return pdf_urls

    def _is_same_paper(self, paper: Paper, result: dict) -> bool:
        if not result.get("downloadUrl"):
            return False
        # Two works with the same title: if both have a DOI, it must be the same one.
        if paper.doi and result.get("doi"):
            return paper.doi.lower() == result["doi"].lower()
        return True

    def _search(self, titles: list[str]) -> list[dict]:
        query = " OR ".join(f'title:"{title}"' for title in titles)
        headers = {"Authorization": f"Bearer {CORE_API_KEY}"} if CORE_API_KEY else {}

        for _ in range(MAX_ATTEMPTS):
            response = requests.get(
                f"{CORE_API_URL}/search/works/",
                params={"q": query, "limit": RESULTS_PER_REQUEST},
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code == TOO_MANY_REQUESTS:
                # CORE says how long to wait; without a key the limits are low.
                time.sleep(int(response.headers.get("Retry-After", DEFAULT_WAIT_SECONDS)))
                continue
            response.raise_for_status()
            return response.json()["results"]

        raise RuntimeError("CORE sigue rechazando las peticiones, inténtalo más tarde.")


def normalize(title: str) -> str:
    # Compare titles ignoring case, accents, punctuation and spacing.
    title = unicodedata.normalize("NFKD", title)
    title = "".join(character for character in title if not unicodedata.combining(character))
    title = re.sub(r"[^\w\s]", " ", title.lower())
    return " ".join(title.split())
