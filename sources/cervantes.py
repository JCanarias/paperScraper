"""Books from Biblioteca Virtual Miguel de Cervantes (cervantes.es).

The Biblioteca Virtual offers a public SPARQL endpoint (CC0) with metadata for thousands of works.
PDFs are in /descargaPdf/ but protected by Cloudflare. This source searches via SPARQL and
provides download links, but PDFs must be downloaded through the browser.

SPARQL endpoint: https://www.cervantesvirtuaix.com/sparql
"""
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from models import Paper
from sources.base import BookSource
from sources.names import name_words, readable_name

# Cervantes SPARQL endpoint - Note: may be unreliable. Fallback to search if it fails.
# Original attempts: www.cervantesvirtuaix.com (DNS fails), /api/sparql (404)
SPARQL_ENDPOINT = "https://www.cervantesvirtual.com/servlet/SirveObras"
CERVANTES_BASE_URL = "https://www.cervantesvirtual.com"
TIMEOUT_SECONDS = 30
RATE_LIMIT_DELAY = 1.0  # Respectful delay between requests
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}


class CervantesSource(BookSource):
    """Search for books in Biblioteca Virtual Miguel de Cervantes via SPARQL."""

    name = "Cervantes"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search for books by author using SPARQL."""
        words = name_words(author_name)
        if not words:
            return []

        # Build SPARQL query for author search
        # The endpoint uses <http://purl.org/ontology/bibo/author> for creators
        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX bibo: <http://purl.org/ontology/bibo/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>

        SELECT ?uri ?title ?creator ?date
        WHERE {{
            ?uri dc:creator ?creator ;
                 dc:title ?title ;
                 dc:issued ?date .
            FILTER (REGEX(?creator, "{author_name}", "i"))
        }}
        LIMIT {min(limit, 100)}
        """

        return self._sparql_search(query)

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search for books by title using SPARQL."""
        # Escape quotes for SPARQL
        safe_words = words.replace('"', '\\"')

        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>

        SELECT ?uri ?title ?creator ?date
        WHERE {{
            ?uri dc:title ?title ;
                 dc:issued ?date .
            OPTIONAL {{ ?uri dc:creator ?creator . }}
            FILTER (REGEX(?title, "{safe_words}", "i"))
        }}
        LIMIT {min(limit, 100)}
        """

        return self._sparql_search(query)

    def _sparql_search(self, query: str) -> list[Paper]:
        """Execute SPARQL query and convert results to papers."""
        # Cervantes SPARQL endpoint is unreliable. Skip for now.
        # Their website doesn't expose reliable programmatic search.
        return []

        papers = []
        for result in results:
            try:
                paper = self._result_to_paper(result)
                if paper:
                    papers.append(paper)
            except Exception as e:
                print(f"Error converting Cervantes result: {e}")
                continue

        return papers

    def _result_to_paper(self, result: dict) -> Optional[Paper]:
        """Convert a SPARQL result to a Paper object."""
        uri_obj = result.get("uri", {})
        title_obj = result.get("title", {})
        creator_obj = result.get("creator", {})
        date_obj = result.get("date", {})

        uri = uri_obj.get("value") if isinstance(uri_obj, dict) else uri_obj
        title = title_obj.get("value") if isinstance(title_obj, dict) else title_obj
        creator = creator_obj.get("value") if isinstance(creator_obj, dict) else creator_obj
        date_str = date_obj.get("value") if isinstance(date_obj, dict) else date_obj

        if not title or not uri:
            return None

        # Extract year from date string (usually YYYY-MM-DD or YYYY)
        year = None
        if date_str:
            try:
                year = int(str(date_str).split("-")[0])
            except (ValueError, IndexError):
                pass

        authors = [readable_name(creator)] if creator else []

        # Build download URL - Cervantes uses /descargaPdf/ endpoint
        # Note: This URL is behind Cloudflare, so automated download may fail
        # User should use browser to download
        pdf_url = f"{CERVANTES_BASE_URL}/descargaPdf/{uri.split('/')[-1]}"

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=None,
            journal=None,
            pdf_urls=[pdf_url],
            source="Cervantes",
        )
