"""The books of the Bavarian State Library (MDZ, digitale-sammlungen.de), as PDF.

Europeana and others link them by the image of a page (bsb-muenchen-digital.de) or by their URN
(mdz-nbn-resolving.de); both carry the book's number ("bsb11273317"). The PDF is made on request by
its download page, which a person uses so: tick that they have read the rights notice (free use, not
commercial), press "WEITER" and, when the file is assembled, open its link. The program does the
same in the browser (browser_session.py), one book at a time and calmly: the whole book, as the
link is to the whole book.
"""
import re
import time
from urllib.parse import urlparse

import requests

import browser_session

MDZ_HOSTS = ("digitale-sammlungen.de", "bsb-muenchen-digital.de", "mdz-nbn-resolving.de")
BOOK_NUMBER = re.compile(r"bsb(\d{8})")
MANIFEST_URL = "https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb{number}/manifest"
FORM_URL = ("https://download.digitale-sammlungen.de/BOOKS/download.pl"
            "?id=bsb{number}&nr=1&ersteseite=1&letzteseite={pages}")
TIMEOUT_SECONDS = 60
# A big book takes a while to be assembled.
ASSEMBLY_TIMEOUT_SECONDS = 600
# Each book is made for us on their server: a long pause between two.
SECONDS_BETWEEN_BOOKS = 30
HEADERS = {"User-Agent": "Mozilla/5.0"}

_last_book = 0.0


def is_mdz_link(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith(MDZ_HOSTS) and BOOK_NUMBER.search(url) is not None


def download_pdf(url: str) -> bytes:
    global _last_book
    number = BOOK_NUMBER.search(url).group(1)
    pages = page_count(number)
    wait = _last_book + SECONDS_BETWEEN_BOOKS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_book = time.monotonic()

    from selenium.webdriver.common.by import By

    driver = browser_session.open_page(FORM_URL.format(number=number, pages=pages))
    # "I confirm that I have read the rights notice", then the first "WEITER": the PDF right away.
    driver.find_element(By.CSS_SELECTOR, "input[name=xdfz][value='2']").click()
    driver.find_elements(By.CSS_SELECTOR, "input.weiterbutton")[0].click()
    deadline = time.monotonic() + ASSEMBLY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        links = driver.execute_script(
            "return [...document.querySelectorAll('a[href$=\".pdf\"]')].map(link => link.href)")
        if links:
            content, _ = browser_session.download(links[0])
            if not content:
                raise ValueError("la Biblioteca de Múnich no ha dado el PDF")
            return content
        time.sleep(2)
    raise ValueError("la Biblioteca de Múnich no ha terminado de preparar el PDF a tiempo")


def page_count(number: str) -> int:
    response = requests.get(MANIFEST_URL.format(number=number), headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return len(response.json()["sequences"][0]["canvases"])
