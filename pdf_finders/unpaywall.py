from concurrent.futures import ThreadPoolExecutor

import requests

from config import UNPAYWALL_API_URL, UNPAYWALL_EMAIL
from pdf_finders.base import DoiPdfFinder

# Unpaywall answers one DOI per request, so we send a few at the same time.
PARALLEL_REQUESTS = 5
TIMEOUT_SECONDS = 30
NOT_FOUND = 404


class UnpaywallFinder(DoiPdfFinder):

    def find_pdf_urls_by_doi(self, dois: list[str]) -> dict[str, list[str]]:
        print(f"[UNPAYWALL] Buscando {len(dois)} DOIs...")
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as executor:
            results = executor.map(self._find_for_doi, dois)
            pdf_urls = {doi: urls for doi, urls in zip(dois, results) if urls}
        print(f"[UNPAYWALL] ✓ {len(pdf_urls)}/{len(dois)} con PDF")
        return pdf_urls

    def _find_for_doi(self, doi: str) -> list[str]:
        try:
            response = requests.get(
                f"{UNPAYWALL_API_URL}/{doi}",
                params={"email": UNPAYWALL_EMAIL},
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code == NOT_FOUND:
                return []
            response.raise_for_status()
        except requests.RequestException:
            # One DOI failing shouldn't stop the others.
            return []

        # Every legal copy Unpaywall knows (publisher, repositories...), best one first.
        # Some copies only have a web page and no direct PDF link; we skip those.
        pdf_urls = []
        for location in response.json()["oa_locations"]:
            if location["url_for_pdf"] and location["url_for_pdf"] not in pdf_urls:
                pdf_urls.append(location["url_for_pdf"])
        return pdf_urls
