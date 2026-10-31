import requests

from config import OPENALEX_API_KEY, OPENALEX_API_URL
from models import Author, Paper
from sources.base import Source

MAX_RESULTS_PER_PAGE = 200
# OpenAlex accepts up to 100 values in one filter, but long URLs fail, so we stay lower.
MAX_DOIS_PER_REQUEST = 50


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
                "filter": f"author.id:{author.id}",
                "per-page": MAX_RESULTS_PER_PAGE,
                "cursor": cursor,
            })
            response.raise_for_status()
            data = response.json()

            papers.extend(self._build_paper(result) for result in data["results"])
            cursor = data["meta"]["next_cursor"]

        return papers

    def get_top_papers(self, author: Author, limit: int) -> list[Paper]:
        # The most cited works tell best who an author is, and only need one request.
        response = self._get(f"{OPENALEX_API_URL}/works", params={
            "filter": f"author.id:{author.id}",
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
                "filter": f"title.search:{words}",
                "sort": "relevance_score:desc",
                "per-page": MAX_RESULTS_PER_PAGE,
                "cursor": cursor,
            })
            response.raise_for_status()
            data = response.json()

            papers.extend(self._build_paper(result) for result in data["results"])
            total = data["meta"]["count"]
            cursor = data["meta"]["next_cursor"]

        return papers[:limit], total

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
        if OPENALEX_API_KEY:
            params = {**params, "api_key": OPENALEX_API_KEY}
        return requests.get(url, params=params)

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
        )

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
            if location["pdf_url"] and location["pdf_url"] not in pdf_urls:
                pdf_urls.append(location["pdf_url"])
        return pdf_urls
