import re
import time

import requests

from duplicates import title_words

from config import OPENALEX_API_KEY, OPENALEX_API_URL
from models import Author, Paper
from sources.base import Source

MAX_RESULTS_PER_PAGE = 200
# Journal pages that OpenAlex records as works ("Consejo editorial", "Índice"...).
NOT_WORKS = "type:!paratext"
# Sites whose terms forbid downloading their files with programs (PhilPapers allows it only
# with written permission); their links are left out, and other copies are tried instead.
NO_PROGRAM_DOWNLOADS = ("philpapers.org", "philarchive.org", "jstor.org", "muse.jhu.edu")
# "https://arxiv.org/abs/1706.03762v5" -> "1706.03762"; old ids look like "math/0211159".
ARXIV_LINK = re.compile(r"arxiv\.org/abs/(.+?)(?:v\d+)?/?(?:[?#]|$)", re.I)
# OpenAlex accepts up to 100 values in one filter, but long URLs fail, so we stay lower.
MAX_DOIS_PER_REQUEST = 50
TIMEOUT_SECONDS = 60
# When OpenAlex says "too many requests" (429) or fails for a moment (5xx), it is asked again after
# these waits; if it still refuses, the error goes up. A longer "Retry-After" from OpenAlex is respected,
# up to MAX_RETRY_AFTER_SECONDS (beyond that it is the daily limit, and waiting doesn't help).
RETRY_WAITS_SECONDS = (5, 30, 120)
MAX_RETRY_AFTER_SECONDS = 600


class OpenAlexSource(Source):
    """Papers and academic books; its works already include the open access books (DOAB, OAPEN...)."""

    def find_authors(self, name: str) -> list[Author]:
        response = self._get(f"{OPENALEX_API_URL}/authors", params={"search": name})
        response.raise_for_status()

        authors = []
        for result in response.json()["results"]:
            # Some authors have no known institution, and OpenAlex returns null instead of [].
            known_institutions = result["last_known_institutions"] or []
            institutions = [institution["display_name"] for institution in known_institutions]
            authors.append(Author(
                id=result["id"],
                name=result["display_name"],
                works_count=result["works_count"],
                institutions=institutions,
            ))
        return authors

    def get_papers(self, author: Author) -> list[Paper]:
        papers = []

        # OpenAlex returns results in pages; the cursor tells us where the next page starts.
        cursor = "*"
        while cursor:
            response = self._get(f"{OPENALEX_API_URL}/works", params={
                "filter": f"author.id:{author.id},{NOT_WORKS}",
                "per-page": MAX_RESULTS_PER_PAGE,
                "cursor": cursor,
            })
            response.raise_for_status()
            data = response.json()

            papers.extend(paper for paper in map(self._build_paper, data["results"]) if not is_front_matter(paper.title))
            cursor = data["meta"]["next_cursor"]

        return papers

    def get_top_papers(self, author: Author, limit: int) -> list[Paper]:
        # The most cited works tell best who an author is, and only need one request.
        response = self._get(f"{OPENALEX_API_URL}/works", params={
            "filter": f"author.id:{author.id},{NOT_WORKS}",
            "sort": "cited_by_count:desc",
            "per-page": limit,
        })
        response.raise_for_status()
        return [self._build_paper(result) for result in response.json()["results"]]

    def search_papers_by_title(self, words: str, limit: int) -> tuple[list[Paper], int]:
        # Commas separate filters in OpenAlex, so they can't appear inside the search text.
        words = words.replace(",", " ")
        papers = []
        total = 0

        cursor = "*"
        while cursor and len(papers) < limit:
            response = self._get(f"{OPENALEX_API_URL}/works", params={
                "filter": f"title.search:{words},{NOT_WORKS}",
                "sort": "relevance_score:desc",
                "per-page": MAX_RESULTS_PER_PAGE,
                "cursor": cursor,
            })
            response.raise_for_status()
            data = response.json()

            papers.extend(paper for paper in map(self._build_paper, data["results"]) if not is_front_matter(paper.title))
            total = data["meta"]["count"]
            cursor = data["meta"]["next_cursor"]

        return papers[:limit], total

    def search_works(self, text: str, limit: int) -> list[Paper]:
        """The works that best match a free text (a bibliography reference, say), best first."""
        response = self._get(f"{OPENALEX_API_URL}/works", params={
            # Commas separate filters in OpenAlex, and some symbols break the search.
            "search": re.sub(r"[,:;()\[\]{}\"]", " ", text),
            "per-page": limit,
        })
        response.raise_for_status()
        return [self._build_paper(result) for result in response.json()["results"]]

    def search_by_title_and_author(self, title: str, surname: str, limit: int) -> list[Paper]:
        """Works with those words in the title and an author with that surname, the most relevant first."""
        # Commas separate filters in OpenAlex, so they can't appear inside the search text.
        title = re.sub(r"[,:;()\[\]{}\"|]", " ", title)
        response = self._get(f"{OPENALEX_API_URL}/works", params={
            "filter": f"title.search:{title},raw_author_name.search:{surname}",
            "per-page": limit,
        })
        response.raise_for_status()
        return [self._build_paper(result) for result in response.json()["results"]]

    def get_papers_by_dois(self, dois: list[str]) -> list[Paper]:
        papers = []
        for start in range(0, len(dois), MAX_DOIS_PER_REQUEST):
            dois_group = dois[start:start + MAX_DOIS_PER_REQUEST]
            response = self._get(f"{OPENALEX_API_URL}/works", params={
                "filter": "doi:" + "|".join(dois_group),
                "per-page": MAX_DOIS_PER_REQUEST,
            })
            response.raise_for_status()
            papers.extend(self._build_paper(result) for result in response.json()["results"])
        return papers

    def _get(self, url: str, params: dict) -> requests.Response:
        """Ask OpenAlex; when it says "too many requests" (or fails for a moment), wait and ask again.

        The errors never show the address: it carries the API key.
        """
        if OPENALEX_API_KEY:
            params = {**params, "api_key": OPENALEX_API_KEY}
        for wait in (*RETRY_WAITS_SECONDS, None):
            try:
                response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
            except requests.RequestException as error:
                problem = f"no responde ({type(error).__name__})"
            else:
                if response.ok:
                    return response
                if response.status_code != 429 and response.status_code < 500:
                    raise OpenAlexError(f"OpenAlex ha respondido {response.status_code}: {answer_message(response)}")
                problem = f"ha respondido {response.status_code}: {answer_message(response)}"
                retry_after = response.headers.get("Retry-After", "")
                if wait is not None and retry_after.isdigit():
                    wait = max(wait, min(int(retry_after), MAX_RETRY_AFTER_SECONDS))
            if wait is None:
                raise OpenAlexError(f"OpenAlex {problem}")
            print(f"  OpenAlex {problem}; se reintenta dentro de {wait} s")
            time.sleep(wait)

    def _build_paper(self, work: dict) -> Paper:
        # The journal (or repository) where the work was published; it can be unknown.
        location_source = (work["primary_location"] or {}).get("source") or {}
        return Paper(
            title=self._title(work),
            year=work["publication_year"],
            doi=self._extract_doi(work),
            pdf_urls=self._find_pdf_urls(work),
            authors=[authorship["author"]["display_name"] for authorship in work["authorships"]],
            publication_date=work.get("publication_date"),
            journal=location_source.get("display_name"),
            volume=(work.get("biblio") or {}).get("volume"),
            publisher=location_source.get("host_organization_name"),
            language=work.get("language"),
            identifiers=self._identifiers(work, location_source),
        )

    def _identifiers(self, work: dict, location_source: dict) -> dict[str, str]:
        # OpenAlex gives most ids as links ("https://pubmed.ncbi.nlm.nih.gov/16873662"); we keep the id.
        ids = work.get("ids") or {}
        identifiers = {
            "openalex": work["id"].rsplit("/", 1)[-1],
            "pmid": (ids.get("pmid") or "").rstrip("/").rsplit("/", 1)[-1],
            "pmcid": (ids.get("pmcid") or "").rstrip("/").rsplit("/", 1)[-1],
            "issn": location_source.get("issn_l") or "",
            "arxiv": self._arxiv_id(work),
        }
        return {scheme: value for scheme, value in identifiers.items() if value}

    def _arxiv_id(self, work: dict) -> str:
        for location in work.get("locations") or []:
            match = ARXIV_LINK.search(location.get("landing_page_url") or "")
            if match:
                return match.group(1)
        return ""

    def _title(self, work: dict) -> str:
        # Some works have no title; the DOI (or id) keeps their file names different.
        if work.get("display_name"):
            return work["display_name"]
        return f"Sin título ({self._extract_doi(work) or work['id'].rsplit('/', 1)[-1]})"

    def _extract_doi(self, work: dict) -> str | None:
        # OpenAlex gives the DOI as a URL ("https://doi.org/10.xxx"); we keep only the DOI itself.
        if work["doi"] is None:
            return None
        return work["doi"].removeprefix("https://doi.org/")

    def _find_pdf_urls(self, work: dict) -> list[str]:
        # A work can be hosted in several places (journal, repositories...).
        # We collect every direct PDF link, skipping repeated ones.
        pdf_urls = []
        for location in work["locations"]:
            url = location["pdf_url"]
            if url and url not in pdf_urls and not any(host in url for host in NO_PROGRAM_DOWNLOADS):
                pdf_urls.append(url)
        return pdf_urls


# Pages of a journal issue that OpenAlex often records as articles; their words, without accents.
# A single word must be the whole title ("Índice"); a phrase may begin it ("Consejo editorial Director").
FRONT_MATTER_TITLES = ("indice", "sumario", "creditos", "contents", "editorial board")
FRONT_MATTER_STARTS = (
    "consejo editorial", "comite editorial", "comite cientifico", "redaccion administracion",
    "normas para autores", "normas de publicacion", "table of contents", "front matter",
    "back matter", "instructions for authors", "issue information",
)


class OpenAlexError(requests.HTTPError):
    """An OpenAlex error whose message doesn't carry the address (nor, in it, the API key)."""


def answer_message(response: requests.Response) -> str:
    """What OpenAlex says about the error, without the address it repeats."""
    try:
        data = response.json()
        message = str(data.get("message") or data.get("error") or "")
    except ValueError:
        message = response.text
    if OPENALEX_API_KEY:
        message = message.replace(OPENALEX_API_KEY, "***")
    return message.strip()[:200] or response.reason


def is_front_matter(title: str | None) -> bool:
    words = " ".join(title_words(title or ""))
    return words in FRONT_MATTER_TITLES or any(
        words == phrase or words.startswith(phrase + " ") for phrase in FRONT_MATTER_STARTS
    )
