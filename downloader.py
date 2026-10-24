import re
from pathlib import Path

import requests
import truststore

from metadata import write_metadata
from models import Paper

TIMEOUT_SECONDS = 30
# Whole books can be large and come from slow servers.
DOWNLOAD_TIMEOUT_SECONDS = 120
MAX_FILENAME_LENGTH = 150
EXTENSIONS = ("pdf", "epub")

# Many journal websites send an incomplete certificate chain. Browsers complete it on their own,
# and so does the operating system's certificate store, so we check certificates with it.
truststore.inject_into_ssl()

# Some websites reject requests that don't look like they come from a browser.
HEADERS = {"User-Agent": "Mozilla/5.0"}


def download_paper(paper: Paper, folder: Path, urls: list[str]) -> bool:
    """Try each link until one gives a PDF or an EPUB; return True if the work ends up downloaded."""
    folder.mkdir(parents=True, exist_ok=True)

    if is_downloaded(paper, folder):
        return True

    for url in urls:
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
    return None


def is_downloaded(paper: Paper, folder: Path) -> bool:
    return downloaded_file(paper, folder) is not None


def download_file(url: str, paper: Paper, folder: Path) -> None:
    response = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    response.raise_for_status()

    # Some links return a web page (a login, a captcha...) instead of the file.
    extension = file_extension(response.content)
    if extension is None:
        raise ValueError("el enlace no devuelve un PDF ni un EPUB")

    file_path = folder / build_filename(paper, extension)
    file_path.write_bytes(response.content)
    add_metadata(file_path, paper)


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


def build_filename(paper: Paper, extension: str = "pdf") -> str:
    # Remove characters that are not allowed in file names.
    title = re.sub(r'[<>:"/\\|?*\n\r\t]', "", paper.title).strip()
    title = title[:MAX_FILENAME_LENGTH]
    # The same book often exists in several languages (Gutenberg, Internet Archive...).
    if paper.source and paper.language:
        title = f"{title} ({paper.language})"
    # Old books (Gutenberg, Internet Archive...) often have no known year.
    if paper.year is None:
        return f"{title}.{extension}"
    return f"{paper.year} - {title}.{extension}"
