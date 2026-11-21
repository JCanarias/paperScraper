import time

import requests

from config import SEMANTIC_SCHOLAR_API_URL
from pdf_finders.base import DoiPdfFinder

MAX_DOIS_PER_REQUEST = 500

# Without an API key, Semantic Scholar often rejects requests for a few seconds
# when it is busy (HTTP 429), so we wait and try again.
TOO_MANY_REQUESTS = 429
BAD_REQUEST = 400
MAX_ATTEMPTS = 5
SECONDS_BETWEEN_ATTEMPTS = 5

# arXiv gives its own DOIs to its papers: 10.48550/arXiv.<arXiv id>.
ARXIV_DOI_PREFIX = "10.48550/arxiv."
ARXIV_PDF_URL = "https://arxiv.org/pdf/{}"


class SemanticScholarFinder(DoiPdfFinder):
    """Open access PDFs known by Semantic Scholar, plus the arXiv version when the paper is also there."""

    def find_pdf_urls_by_doi(self, dois: list[str]) -> dict[str, list[str]]:
        pdf_urls = {}

        for start in range(0, len(dois), MAX_DOIS_PER_REQUEST):
            dois_group = dois[start:start + MAX_DOIS_PER_REQUEST]
            paper_records = self._request_papers(dois_group)

            # Results come in the same order as the DOIs we sent.
            # The record is None when Semantic Scholar doesn't know that paper.
            for doi, paper_record in zip(dois_group, paper_records):
                urls = self._pdf_urls(doi, paper_record)
                if urls:
                    pdf_urls[doi] = urls

        return pdf_urls

    def _pdf_urls(self, doi: str, paper_record: dict | None) -> list[str]:
        urls = []
        if doi.lower().startswith(ARXIV_DOI_PREFIX):
            urls.append(ARXIV_PDF_URL.format(doi[len(ARXIV_DOI_PREFIX):]))
        if paper_record:
            if paper_record["openAccessPdf"] and paper_record["openAccessPdf"]["url"]:
                urls.append(paper_record["openAccessPdf"]["url"])
            arxiv_id = (paper_record["externalIds"] or {}).get("ArXiv")
            if arxiv_id:
                urls.append(ARXIV_PDF_URL.format(arxiv_id))
        # The same link can come from two places.
        return list(dict.fromkeys(urls))

    def _request_papers(self, dois: list[str]) -> list[dict | None]:
        for _ in range(MAX_ATTEMPTS):
            response = requests.post(
                f"{SEMANTIC_SCHOLAR_API_URL}/paper/batch",
                params={"fields": "openAccessPdf,externalIds"},
                json={"ids": [f"DOI:{doi}" for doi in dois]},
            )
            if response.status_code == TOO_MANY_REQUESTS:
                time.sleep(SECONDS_BETWEEN_ATTEMPTS)
                continue
            # When it knows none of the DOIs, it answers with an error instead of a list of None.
            if response.status_code == BAD_REQUEST and "No valid paper ids" in response.text:
                return [None] * len(dois)

            response.raise_for_status()
            return response.json()

        raise RuntimeError("Semantic Scholar sigue rechazando las peticiones, inténtalo más tarde.")
