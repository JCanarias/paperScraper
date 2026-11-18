"""The copy in Internet Archive of a HathiTrust or Google Books book, which are not downloaded from there.

HathiTrust blocks downloads by programs ("Blocked from HathiTrust") and its terms forbid them, as
Google's do. But many of their scans are also in Internet Archive, which lets programs download:
- Google Books: Internet Archive keeps the address of the Google scan each copy came from (its
  "source" field), so the copy of the same scan is found by the book's Google id.
- HathiTrust: its catalogue API (which programs may use) gives the book's OCLC number and year;
  Internet Archive's copies with that number and that year, and not a single volume of a set, are
  the same edition (an OCLC number alone groups different editions and volumes).
"""
import re
from urllib.parse import urlparse

import requests

from sources.internet_archive import LENDING_COLLECTIONS, InternetArchiveSource

HATHI_VOLUME = re.compile(r"[?;&]id=([^;&#]+)")
GOOGLE_VOLUME = re.compile(r"[?&]id=([\w-]{12})\b")
HATHI_CATALOG_URL = "https://catalog.hathitrust.org/api/volumes/brief/htid/{volume}.json"
SEARCH_URL = "https://archive.org/advancedsearch.php"
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
TIMEOUT_SECONDS = 60
MAX_COPIES = 5


def is_hathitrust_link(url: str) -> bool:
    return (urlparse(url).hostname or "").endswith("hathitrust.org") and HATHI_VOLUME.search(url) is not None


def is_google_books_link(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.startswith("books.google.") and GOOGLE_VOLUME.search(url) is not None


def copy_urls(url: str) -> list[str]:
    """The file addresses of the book's copies in Internet Archive, the best first."""
    if is_hathitrust_link(url):
        identifiers = hathitrust_copies(HATHI_VOLUME.search(url).group(1))
    elif is_google_books_link(url):
        identifiers = google_books_copies(GOOGLE_VOLUME.search(url).group(1))
    else:
        return []
    archive = InternetArchiveSource()
    return [file_url for identifier in identifiers[:MAX_COPIES] for file_url in archive._find_file_urls(identifier)]


def hathitrust_copies(volume: str) -> list[str]:
    response = requests.get(HATHI_CATALOG_URL.format(volume=volume), headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    records = response.json().get("records", {}).values()
    oclcs = [number for record in records for number in record.get("oclcs", []) if number.isdigit()]
    years = {date[:4] for record in records for date in record.get("publishDates", [])}
    if not oclcs or not years:
        return []
    items = search(" OR ".join(f"oclc-id:{number}" for number in oclcs))
    return [item["identifier"] for item in items
            if str(item.get("date", ""))[:4] in years and not item.get("volume")]


def google_books_copies(google_id: str) -> list[str]:
    same_scan = re.compile(rf"[?&]id={re.escape(google_id)}(?:&|$)")
    items = search(f'source:"{google_id}"')
    return [item["identifier"] for item in items
            if any(same_scan.search(source) for source in as_list(item.get("source")))]


def search(query: str) -> list[dict]:
    excluded = " AND ".join(f"-collection:{collection}" for collection in LENDING_COLLECTIONS)
    response = requests.get(SEARCH_URL, params={
        "q": f"({query}) AND mediatype:texts AND {excluded} AND -access-restricted-item:true",
        "fl[]": ["identifier", "date", "volume", "source"], "rows": 20, "output": "json",
    }, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()["response"]["docs"]


def as_list(value) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in value] if isinstance(value, list) else [str(value)]
