import html
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import truststore

import browser_session
import gallica_pages
import internet_archive_copies
import mdz
from pdf_finders.core import core_output_id, source_urls
from metadata import write_metadata
from models import Paper

TIMEOUT_SECONDS = 30
# Whole books can be large and come from slow servers.
DOWNLOAD_TIMEOUT_SECONDS = 120
# The tags that point to the file are in the <head>, at the start of the page.
PAGE_HEAD_LENGTH = 200_000
MAX_FILENAME_LENGTH = 150
MAX_AUTHORS_IN_FILENAME = 2
MAX_AUTHORS_LENGTH = 60
EXTENSIONS = ("pdf", "epub")
# Characters that are not allowed in Windows file names.
FORBIDDEN_CHARACTERS = r'[<>:"/\\|?*\n\r\t]'

# Many journal websites send an incomplete certificate chain. Browsers complete it on their own,
# and so does the operating system's certificate store, so we check certificates with it.
truststore.inject_into_ssl()

# Some websites reject requests that don't look like they come from a browser.
HEADERS = {"User-Agent": "Mozilla/5.0"}
# Wikimedia asks programs to say who they are; to a browser-like name its EPUB maker
# answers with a "you're not a bot?" page instead of the book.
HONEST_HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
HONEST_HOSTS = ("ws-export.wmcloud.org", "wikisource.org", "wikimedia.org")
# The titles of the check pages that a real browser passes on its own, with no click: Anubis (many
# university repositories: Valencia, Salamanca, UPM...), PubMed Central, the Universidad de Chile.
BROWSER_CHECK_TITLES = ("making sure you&#39;re not a bot", "making sure you're not a bot", "preparing to download",
                        "checking your browser", "verificando acceso")
# Their works are only downloaded by hand: the BNE blocked the program. Their links are the pages opened
# for the user. Gallica's books are made from the images of their pages (gallica_pages.py), and HathiTrust's
# and Google's are looked for in Internet Archive (internet_archive_copies.py).
MANUAL_ONLY_HOSTS = ("bnedigital.bne.es",)
# Their other links (a PDF, a catalogue record...) are not followed: Gallica blocks the browser for the rest
# of the run when it asks for a PDF, and HathiTrust and Google don't let programs download.
NOT_FOLLOWED_HOSTS = ("gallica.bnf.fr", "hathitrust.org", "books.google.com", "books.google.es")


def headers_for(url: str) -> dict[str, str]:
    host = urlparse(url).hostname or ""
    return HONEST_HEADERS if host.endswith(HONEST_HOSTS) else HEADERS


def download_paper(paper: Paper, folder: Path, urls: list[str]) -> bool:
    """Try each link until one gives a PDF or an EPUB; return True if the work ends up downloaded."""
    folder.mkdir(parents=True, exist_ok=True)

    if is_downloaded(paper, folder):
        return True

    for url in urls:
        if (urlparse(url).hostname or "").endswith(MANUAL_ONLY_HOSTS):
            continue
        try:
            download_file(url, paper, folder)
            return True
        except Exception:
            continue

    return False


def downloaded_file(paper: Paper, folder: Path) -> Path | None:
    for extension in EXTENSIONS:
        file_path = folder / build_filename(paper, extension)
        if file_path.exists():
            return file_path
        # Files downloaded before the authors were in the name get the new name now.
        old_path = folder / build_filename(paper, extension, with_authors=False)
        if old_path != file_path and old_path.exists():
            old_path.rename(file_path)
            return file_path
    return None


def is_downloaded(paper: Paper, folder: Path) -> bool:
    return downloaded_file(paper, folder) is not None


def download_file(url: str, paper: Paper, folder: Path) -> None:
    # The Munich library makes its PDFs on request, through a form (mdz.py).
    if mdz.is_mdz_link(url):
        content = mdz.download_pdf(url)
        if file_extension(content) is None:
            raise ValueError("la Biblioteca de Múnich no ha dado un PDF")
        save_file(content, "pdf", paper, folder)
        return
    if gallica_pages.is_gallica_link(url):
        save_file(gallica_pages.download_pdf(url), "pdf", paper, folder)
        return
    # HathiTrust and Google don't let programs download; the same scan in Internet Archive does.
    if internet_archive_copies.is_hathitrust_link(url) or internet_archive_copies.is_google_books_link(url):
        for copy_url in internet_archive_copies.copy_urls(url):
            try:
                download_file(copy_url, paper, folder)
                return
            except Exception:
                continue
        raise ValueError("no hay copia del libro en Internet Archive")
    if (urlparse(url).hostname or "").endswith(NOT_FOLLOWED_HOSTS):
        raise ValueError("este enlace solo se abre a mano")
    # CORE's copy can't be reached; the repository it came from usually can.
    output_id = core_output_id(url)
    if output_id:
        for source_url in source_urls(output_id):
            try:
                download_file(source_url, paper, folder)
                return
            except Exception:
                continue
        raise ValueError("ni CORE ni el repositorio de donde lo sacó dan el archivo")

    content, page, page_url = fetch(url)

    # Repositories and journals often link to the work's page instead of its file; that page
    # says where the file is in a "citation_pdf_url" tag (the one Google Scholar reads).
    extension = file_extension(content)
    if extension is None:
        pdf_link = pdf_link_in_html(page, page_url)
        if pdf_link and pdf_link != url:
            content, _, _ = fetch(pdf_link)
            extension = file_extension(content)

    # Some links return a web page (a login, a captcha...) instead of the file.
    if extension is None:
        raise ValueError("el enlace no devuelve un PDF ni un EPUB")

    save_file(content, extension, paper, folder)


def fetch(url: str) -> tuple[bytes, str, str]:
    """The answer at the address: its bytes, and its text when it is a web page, and the final address."""
    # Some websites only let a real browser in (a Cloudflare check): those go through one (browser_session.py).
    if browser_session.needs_browser(url):
        content, page = browser_session.download(url)
        return content or b"", page, url
    headers = headers_for(url)
    response = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    # Anubis, and some other filters (Zenodo), stop the programs that pass for a browser but let in
    # the ones that say who they are: asked again once with the program's own name.
    if headers is HEADERS and not behind_cloudflare_check(response) and (
            response.status_code in (403, 429) or page_title(response).startswith(BROWSER_CHECK_TITLES)):
        response = requests.get(url, headers=HONEST_HEADERS, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    # The same check on a website not in the list, or reached through a redirect (doi.org,
    # hdl.handle.net): the browser opens the address where the check was, only then.
    if browser_session.needs_browser(response.url) or behind_browser_check(response):
        content, page = browser_session.download(response.url)
        return content or b"", page, response.url
    response.raise_for_status()
    page = response.text if "html" in response.headers.get("content-type", "") else ""
    return response.content, page, response.url


def behind_browser_check(response: requests.Response) -> bool:
    """A check page that a real browser usually passes: Cloudflare's, Amazon's (De Gruyter) and others."""
    return (behind_cloudflare_check(response) or response.headers.get("x-amzn-waf-action") == "challenge"
            or page_title(response).startswith(BROWSER_CHECK_TITLES))


def page_title(response: requests.Response) -> str:
    if "html" not in response.headers.get("content-type", ""):
        return ""
    title = re.search(r"<title[^>]*>(.*?)</title>", response.text[:PAGE_HEAD_LENGTH], re.S | re.I)
    return title.group(1).strip().lower() if title else ""


def behind_cloudflare_check(response: requests.Response) -> bool:
    """Cloudflare's check page, or its "you have been blocked" one, which a real browser usually passes
    (RACO, TDX: their robots.txt lets every program in)."""
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    return response.status_code == 403 and response.headers.get("server", "").lower() == "cloudflare"


def save_file(content: bytes, extension: str, paper: Paper, folder: Path) -> None:
    file_path = folder / build_filename(paper, extension)
    file_path.write_bytes(content)
    add_metadata(file_path, paper)


def pdf_link_in_html(page: str, page_url: str) -> str | None:
    for tag in re.findall(r"<meta[^>]+>", page[:PAGE_HEAD_LENGTH], re.I):
        if re.search(r'name=["\'](?:citation_pdf_url|bepress_citation_pdf_url|eprints\.document_url)["\']', tag, re.I):
            link = re.search(r'content=["\']([^"\']+)["\']', tag, re.I)
            if link:
                address = urlparse(urljoin(page_url, html.unescape(link.group(1))))
                # Some repositories (DSpace 7: Valencia) give their server's inner address
                # ("http://localhost:4000/bitstreams/..."): the same path, on the page's website.
                if address.hostname in ("localhost", "127.0.0.1"):
                    page = urlparse(page_url)
                    address = address._replace(scheme=page.scheme, netloc=page.netloc)
                return address.geturl()
    return None


def file_extension(content: bytes) -> str | None:
    # Every PDF starts with "%PDF". An EPUB is a ZIP file ("PK") whose first entry says what it is.
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.startswith(b"PK") and b"application/epub+zip" in content[:100]:
        return "epub"
    return None


def add_metadata(file_path: Path, paper: Paper) -> None:
    # The file is already saved; if it can't be tagged (a damaged file...), we keep it as it is.
    try:
        write_metadata(file_path, paper)
    except Exception as error:
        print(f"  Aviso: no se han podido escribir los metadatos: {error}")


def tag_repeated_filenames(papers: list[Paper]) -> None:
    """Give a different file name to works of the same list that would share one.

    The one with the lowest DOI keeps the plain name, so the choice is the same every time
    and the files downloaded before keep being found.
    """
    groups: dict[str, list[Paper]] = {}
    for paper in papers:
        paper.filename_tag = None
        groups.setdefault(build_filename(paper).lower(), []).append(paper)

    for group in groups.values():
        group.sort(key=lambda paper: (paper.doi or "~", paper.title or ""))
        for paper in group[1:]:
            paper.filename_tag = paper.doi or paper.source or "2"
    # Two works without DOI from the same source could still clash; number them.
    groups = {}
    for paper in papers:
        groups.setdefault(build_filename(paper).lower(), []).append(paper)
    for group in groups.values():
        group.sort(key=lambda paper: (paper.title or "", paper.source or "", paper.language or ""))
        for number, paper in enumerate(group[1:], start=2):
            paper.filename_tag = f"{paper.filename_tag or ''} {number}".strip()


def build_filename(paper: Paper, extension: str = "pdf", with_authors: bool = True) -> str:
    """Year - Title - Authors.pdf. Without authors, it is the name files had before."""
    # Remove characters that are not allowed in file names.
    title = re.sub(FORBIDDEN_CHARACTERS, "", paper.title or "Sin título").strip()
    title = title[:MAX_FILENAME_LENGTH]
    authors = filename_authors(paper.authors)
    if with_authors and authors:
        title = f"{title} - {authors}"
    # The same book often exists in several languages (Gutenberg, Internet Archive...).
    if paper.source and paper.language:
        title = f"{title} ({paper.language})"
    if paper.filename_tag:
        tag = re.sub(FORBIDDEN_CHARACTERS, "_", paper.filename_tag)
        title = f"{title} [{tag}]"
    # Old books (Gutenberg, Internet Archive...) often have no known year.
    if paper.year is None:
        return f"{title}.{extension}"
    return f"{paper.year} - {title}.{extension}"


def filename_authors(authors: list[str]) -> str:
    # Like Calibre, two authors are joined with "&"; with more, only the first one and "et al.".
    names = [re.sub(FORBIDDEN_CHARACTERS, "", name).strip() for name in authors]
    names = [name for name in names if name]
    if len(names) > MAX_AUTHORS_IN_FILENAME:
        # Without the final dot, so the name doesn't end in "et al..pdf".
        text = f"{names[0]} et al"
    else:
        text = " & ".join(names)
    return text[:MAX_AUTHORS_LENGTH].strip()
