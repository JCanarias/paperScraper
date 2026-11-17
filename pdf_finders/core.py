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


# CORE's own file links (core.ac.uk/download/123.pdf) are behind a Cloudflare check that not even a
# real browser passes. Its API, also without a key, says which repository each file came from.
CORE_DOWNLOAD_LINK = re.compile(r"core\.ac\.uk/download/(?:pdf/)?(\d+)")
# Without a key CORE answers few requests in a row: a calm pace.
SECONDS_BETWEEN_RECORDS = 6
HONEST_HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
# Without a key CORE can ask to wait for a long time: past this, it is left for the rest of the run.
LONGEST_WAIT_SECONDS = 60
_last_record = 0.0
_given_up = False


def core_output_id(url: str) -> str | None:
    match = CORE_DOWNLOAD_LINK.search(url)
    return match.group(1) if match else None


def source_urls(output_id: str) -> list[str]:
    """The addresses of the work in the repository where CORE found it."""
    global _last_record, _given_up
    if _given_up:
        return []
    headers = dict(HONEST_HEADERS)
    if CORE_API_KEY:
        headers["Authorization"] = f"Bearer {CORE_API_KEY}"
    for _ in range(MAX_ATTEMPTS):
        wait = _last_record + SECONDS_BETWEEN_RECORDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_record = time.monotonic()
        response = requests.get(f"{CORE_API_URL}/outputs/{output_id}", headers=headers, timeout=TIMEOUT_SECONDS)
        if response.status_code == TOO_MANY_REQUESTS:
            wait = int(response.headers.get("Retry-After", DEFAULT_WAIT_SECONDS))
            if wait > LONGEST_WAIT_SECONDS:
                break
            time.sleep(wait)
            continue
        response.raise_for_status()
        return [url for url in response.json().get("sourceFulltextUrls") or [] if "core.ac.uk" not in url]
    _given_up = True
    print("  Aviso: CORE no responde a más peticiones; sus copias se dejan para otro día.")
    return []
