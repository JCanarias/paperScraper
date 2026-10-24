import json
import os
from pathlib import Path
from urllib.parse import quote

import cloudscraper
from dotenv import load_dotenv
from requests.cookies import RequestsCookieJar

from pdf_finders.base import DoiPdfFinder

load_dotenv()
API_URL = os.getenv("CUSTOM_LEGAL_SOURCE_API_URL")
if API_URL and not API_URL.endswith("/"):
    API_URL += "/"

# Fallback mirrors in case primary URL is down
FALLBACK_MIRRORS = [
    "https://sci-hub.se/",
    "https://sci-hub.st/",
    "https://sci-hub.ru/",
]

COOKIES_FILE = Path("sci_hub_cookies.json")


def _load_cookies():
    """Load cookies from file if available."""
    if COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE) as f:
                cookies_dict = json.load(f)
            jar = RequestsCookieJar()
            for name, value in cookies_dict.items():
                jar.set(name, value)
            print(f"[SCI-HUB] ✓ {len(cookies_dict)} cookies cargadas desde {COOKIES_FILE}")
            return jar
        except Exception as e:
            print(f"[SCI-HUB] ✗ Error al cargar cookies: {e}")
    else:
        print(f"[SCI-HUB] ⚠ Archivo de cookies no encontrado: {COOKIES_FILE}")
    return None


scraper = cloudscraper.create_scraper()
cookies = _load_cookies()
if cookies:
    scraper.cookies = cookies
else:
    print("[SCI-HUB] ⚠ Sin cookies - los requests pueden ser bloqueados por CAPTCHA")


class CustomLegalSourceFinder(DoiPdfFinder):
    """Sci-hub access disabled - CAPTCHA blocks automated access.

    Sci-hub has per-request CAPTCHA verification. Even after solving CAPTCHA once,
    each individual paper request triggers another CAPTCHA. This prevents reliable automation.

    Alternatives:
    - Use open-access sources (Nature, PLOS, BMC, etc.) - already working
    - Download manually from sci-hub in your browser
    - Use APIs like Unpaywall for open-access research
    """

    def find_pdf_urls_by_doi(self, dois: list[str]) -> dict[str, list[str]]:
        return {}
