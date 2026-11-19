"""The books of Gallica (the Bibliothèque nationale de France), as PDF, from the images of their pages.

Gallica blocks its PDFs to programs (Cloudflare refuses them outright), but it offers the images
of every page through its IIIF API (api.bnf.fr: free access, as long as it isn't abused; reuse of
public domain works is free if not commercial). That API is behind Cloudflare's check too, which the
browser passes (browser_session.py). So the browser reads the book's list of pages (its IIIF
manifest) and asks for each image, one after another and calmly, and the program joins them in a
PDF: a scan without text layer, as a person would get by saving the pages.
"""
import base64
import json
import re
import time
from urllib.parse import urlparse

import browser_session
import task_progress
from page_images import images_to_pdf

GALLICA_BOOK = re.compile(r"/ark:/12148/([a-z0-9]+)")
MANIFEST_URL = "https://gallica.bnf.fr/iiif/ark:/12148/{ark}/manifest.json"
# Wide enough to read the text well (about 160 ppp for an octavo), much lighter than the original.
PAGE_WIDTH = 1300
# A calm pause between two pages, besides the time each one takes.
SECONDS_BETWEEN_PAGES = 1.0
# A long pause between two books.
SECONDS_BETWEEN_BOOKS = 30
# Larger "books" are usually collections of volumes or periodicals: not worth so many requests.
MAX_PAGES = 1500
# Each book is hundreds of requests: a few books in each run (a daily check, a retry), the rest another day.
MAX_BOOKS_PER_RUN = 8
PAGE_TIMEOUT_SECONDS = 120
# A long book takes a while: the log says how it goes.
PROGRESS_EVERY = 50
# The image is read inside the page, where the browser has passed the check (base64, in pieces:
# a long string in one go is too big for the browser).
FETCH_IMAGE = """const done = arguments[arguments.length - 1];
fetch(arguments[0]).then(answer => answer.ok
  ? answer.arrayBuffer().then(buffer => {
      let text = ''; const bytes = new Uint8Array(buffer);
      for (let i = 0; i < bytes.length; i += 32768) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
      done([answer.status, btoa(text)]);
    })
  : done([answer.status, ''])).catch(error => done([String(error), '']));"""

_last_book = 0.0
_books_this_run = 0


def is_gallica_link(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("gallica.bnf.fr") and GALLICA_BOOK.search(url) is not None


def download_pdf(url: str) -> bytes:
    global _last_book, _books_this_run
    ark = GALLICA_BOOK.search(url).group(1)
    if _books_this_run >= MAX_BOOKS_PER_RUN:
        raise ValueError("ya se han bajado bastantes libros de Gallica hoy; este, otro día")
    _books_this_run += 1
    wait = _last_book + SECONDS_BETWEEN_BOOKS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_book = time.monotonic()

    # Chrome shows the JSON as text in the page; the page also lets the images be asked for.
    driver = browser_session.open_page(MANIFEST_URL.format(ark=ark))
    manifest = json.loads(driver.execute_script("return document.body.innerText"))
    canvases = manifest["sequences"][0]["canvases"]
    if len(canvases) > MAX_PAGES:
        raise ValueError(f"el documento de Gallica tiene {len(canvases)} páginas: demasiadas")

    driver.set_script_timeout(PAGE_TIMEOUT_SECONDS)
    pages = []
    for canvas in canvases:
        service = canvas["images"][0]["resource"]["service"]["@id"]
        status, data = driver.execute_async_script(FETCH_IMAGE, f"{service}/full/{PAGE_WIDTH},/0/native.jpg")
        if status != 200 or not data:
            raise ValueError(f"Gallica no ha dado la página {len(pages) + 1} ({status})")
        pages.append(base64.b64decode(data))
        task_progress.detail(f"Gallica: página {len(pages)} de {len(canvases)}")
        if len(pages) % PROGRESS_EVERY == 0:
            print(f"  Gallica: página {len(pages)} de {len(canvases)}", flush=True)
        time.sleep(SECONDS_BETWEEN_PAGES)
    return images_to_pdf(pages)

