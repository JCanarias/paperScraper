"""Spanish books from Biblioteca Digital Hispánica (BNE).

The BNE publishes a public catalogue (CC BY 4.0) at datosabiertos.bne.es with 1,930 works
in open domain or freely distributed. The catalogue includes author, title, date, and a
link to the BNE platform.

PDFs are not directly downloadable via API (Cloudflare protection). This source:
1. Searches the public catalogue
2. Attempts to find copies in Internet Archive
3. Falls back to browser-based download links

Data source: https://datosabiertos.bne.es/catalogo
"""
import csv
import io
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from models import Paper
from sources.base import BookSource
from sources.internet_archive import InternetArchiveSource
from sources.names import name_words, readable_name, same_author

# BNE public data CSV URL
BNE_CATALOGUE_URL = "https://datosabiertos.bne.es/resource/t31p_catalogo_de_fondos_en_dominio_publico_o_libremente_distribuibles/descarga/t31p_catalogo_de_fondos_en_dominio_publico_o_libremente_distribuibles_csv.csv"
BNE_RECORD_URL = "https://bndigital.bne.es/details/"
TIMEOUT_SECONDS = 30
RATE_LIMIT_DELAY = 1.0  # Respectful delay

_bne_cache: Optional[dict] = None
_cache_timestamp: float = 0


class BNESource(BookSource):
    """Search for Spanish public domain books in Biblioteca Digital Hispánica."""

    name = "BNE"

    def __init__(self):
        self.internet_archive = InternetArchiveSource()

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search BNE catalogue for books by author."""
        catalogue = self._load_catalogue()
        if not catalogue:
            return []

        words = name_words(author_name)
        if not words:
            return []

        results = []
        for row in catalogue:
            try:
                if self._author_matches(row.get("Autor"), author_name, words):
                    paper = self._row_to_paper(row)
                    if paper:
                        results.append(paper)
                        if len(results) >= limit:
                            break
            except Exception:
                continue

        return results

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search BNE catalogue for books by title."""
        catalogue = self._load_catalogue()
        if not catalogue:
            return []

        results = []
        for row in catalogue:
            try:
                title = row.get("Título", "").lower()
                if any(word.lower() in title for word in words.split()):
                    paper = self._row_to_paper(row)
                    if paper:
                        results.append(paper)
                        if len(results) >= limit:
                            break
            except Exception:
                continue

        return results

    def _load_catalogue(self) -> Optional[list[dict]]:
        """Load BNE public catalogue CSV."""
        global _bne_cache, _cache_timestamp
        import time as time_module

        # Cache for 24 hours
        if _bne_cache and (time_module.time() - _cache_timestamp) < 86400:
            return _bne_cache

        try:
            time.sleep(RATE_LIMIT_DELAY)
            response = requests.get(
                BNE_CATALOGUE_URL,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "paperScraper/1.0 (research tool)"},
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"BNE catalogue download failed: {e}")
            return None

        try:
            # Parse CSV from response text
            csv_reader = csv.DictReader(io.StringIO(response.text), delimiter=",")
            _bne_cache = list(csv_reader)
            _cache_timestamp = time_module.time()
            print(f"Loaded BNE catalogue: {len(_bne_cache)} works")
            return _bne_cache
        except Exception as e:
            print(f"Error parsing BNE CSV: {e}")
            return None

    @staticmethod
    def _author_matches(csv_author: str, search_name: str, words: list[str]) -> bool:
        """Check if CSV author matches search."""
        if not csv_author:
            return False
        csv_author_lower = csv_author.lower()
        return (
            search_name.lower() in csv_author_lower
            or any(word.lower() in csv_author_lower for word in words)
        )

    def _row_to_paper(self, row: dict) -> Optional[Paper]:
        """Convert a BNE CSV row to Paper object."""
        title = row.get("Título", "").strip()
        if not title:
            return None

        author = row.get("Autor", "").strip()
        year_str = row.get("Fecha_de_publicacion", "").strip()
        bne_id = row.get("Identificador", "").strip()
        bne_url = row.get("URL", "").strip()

        year = None
        if year_str:
            try:
                year = int(year_str.split("-")[0])
            except (ValueError, IndexError):
                pass

        # Build download URL
        pdf_urls = []
        if bne_url:
            pdf_urls.append(bne_url)

        # Try to find in Internet Archive as well
        if title:
            ia_results = self.internet_archive.search_books_by_title(title, 1)
            if ia_results and ia_results[0].pdf_urls:
                pdf_urls.extend(ia_results[0].pdf_urls)

        return Paper(
            title=title,
            authors=[readable_name(author)] if author else [],
            year=year,
            doi=None,
            journal=None,
            pdf_urls=pdf_urls[:1],  # Primary source is BNE
            source="BNE",
        )
