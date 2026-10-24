from abc import ABC, abstractmethod

from models import Paper


class PdfFinder(ABC):
    """Common interface for services that find PDF links for papers."""

    @abstractmethod
    def find_pdf_urls(self, papers: list[Paper]) -> dict[int, list[str]]:
        """Return the PDF links found for each paper, as {position of the paper in the list: [pdf_url, ...]}."""


class DoiPdfFinder(PdfFinder):
    """For services that can only search by DOI: papers without one are skipped."""

    def find_pdf_urls(self, papers: list[Paper]) -> dict[int, list[str]]:
        # DOIs are not case sensitive, and different services write them differently.
        positions = {}
        for position, paper in enumerate(papers):
            if paper.doi:
                positions.setdefault(paper.doi.lower(), []).append(position)
        if not positions:
            return {}

        pdf_urls = {}
        for doi, urls in self.find_pdf_urls_by_doi(list(positions)).items():
            for position in positions.get(doi.lower(), []):
                pdf_urls[position] = urls
        return pdf_urls

    @abstractmethod
    def find_pdf_urls_by_doi(self, dois: list[str]) -> dict[str, list[str]]:
        """Return the PDF links found for each DOI that has any, as {doi: [pdf_url, ...]}."""
