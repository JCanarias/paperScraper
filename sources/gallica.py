"""Books from Gallica - Biblioteca Digital de Francia.

Gallica is the French National Library's digital collection. It offers:
- SRU search API for bibliographic data
- Millions of digitized books, maps, manuscripts

Downloads are behind Cloudflare, but metadata is freely available.
This source searches via SRU and provides browser links.

SRU Documentation: https://gallica.bnf.fr/services/Engine.html
"""
import time
from typing import Optional
from urllib.parse import urlencode, quote
import xml.etree.ElementTree as ET

import requests

from models import Paper
from sources.base import BookSource
from sources.names import readable_name

GALLICA_SRU_URL = "https://gallica.bnf.fr/SRU"
GALLICA_BASE_URL = "https://gallica.bnf.fr"
TIMEOUT_SECONDS = 30
RATE_LIMIT_DELAY = 1.0  # Respectful delay


class GallicaSource(BookSource):
    """Search Gallica (French National Library) via SRU protocol."""

    name = "Gallica"

    def search_books_by_author(self, author_name: str, limit: int) -> list[Paper]:
        """Search Gallica by author."""
        # CQL: Common Query Language for SRU
        query = f'dc.creator any "{author_name}"'
        return self._search(query, limit)

    def search_books_by_title(self, words: str, limit: int) -> list[Paper]:
        """Search Gallica by title."""
        query = f'dc.title any "{words}"'
        return self._search(query, limit)

    def _search(self, query: str, limit: int) -> list[Paper]:
        """Execute SRU search."""
        try:
            time.sleep(RATE_LIMIT_DELAY)
            response = requests.get(
                GALLICA_SRU_URL,
                params={
                    "operation": "searchRetrieve",
                    "version": "1.2",
                    "query": query,
                    "maximumRecords": min(limit, 50),
                    "recordSchema": "oai_dc",
                    "startRecord": 1,
                },
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "paperScraper/1.0 (research tool)"},
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Gallica search failed: {e}")
            return []

        papers = []
        try:
            root = ET.fromstring(response.content)

            # SRU namespace
            ns = {
                "srw": "http://www.loc.gov/zing/srw/",
                "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
                "dc": "http://purl.org/dc/elements/1.1/",
            }

            records = root.findall(".//srw:record", ns)
            for record in records:
                try:
                    paper = self._record_to_paper(record, ns)
                    if paper:
                        papers.append(paper)
                        if len(papers) >= limit:
                            break
                except Exception:
                    continue
        except ET.ParseError as e:
            print(f"Error parsing Gallica XML: {e}")

        return papers

    def _record_to_paper(self, record: ET.Element, ns: dict) -> Optional[Paper]:
        """Convert SRU record to Paper."""
        # Extract Dublin Core metadata
        data = record.find(".//oai_dc:dc", ns)
        if data is None:
            return None

        title_elem = data.find("dc:title", ns)
        title = title_elem.text if title_elem is not None and title_elem.text else None
        if not title:
            return None

        # Extract creators/authors
        authors = []
        for creator in data.findall("dc:creator", ns):
            if creator.text:
                authors.append(readable_name(creator.text))

        # Extract date
        year = None
        for date_elem in data.findall("dc:date", ns):
            if date_elem.text:
                try:
                    year = int(str(date_elem.text).split("-")[0])
                    break
                except (ValueError, IndexError):
                    pass

        # Extract identifier (typically Gallica ARK or URL)
        identifier = None
        for ident in data.findall("dc:identifier", ns):
            if ident.text:
                identifier = ident.text
                break

        # Build Gallica URL
        pdf_urls = []
        if identifier:
            # Try to extract ARK or build URL
            if "gallica.bnf.fr" in identifier:
                pdf_urls.append(identifier)
            else:
                # Assume it's an ARK identifier
                pdf_urls.append(f"{GALLICA_BASE_URL}/ark:/{identifier}")

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=None,
            journal=data.find("dc:publisher", ns).text if data.find("dc:publisher", ns) is not None else None,
            pdf_urls=pdf_urls,
            source="Gallica",
        )
