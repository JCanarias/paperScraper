"""Helps to download by hand the works the program couldn't get on its own.

Some websites only give their files to a person (a captcha, a Cloudflare check, a login).
For each work we open its page in the user's browser; the user downloads the file, and we take
the newest PDF or EPUB from the Downloads folder, rename it, write its metadata and file it.
"""
import os
import shutil
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

import questionary

from downloader import add_metadata, build_filename, file_extension
from models import Paper

DOWNLOADS_FOLDER = Path(os.environ.get("DOWNLOADS_FOLDER", "") or Path.home() / "Downloads")
# Browsers write a partial file first (.crdownload, .part) and rename it when it's complete.
PARTIAL_SUFFIXES = (".crdownload", ".part", ".tmp", ".download")


def download_by_hand(papers: list[Paper], folder: Path) -> int:
    """Return how many works were downloaded by hand."""
    print(f"\nSe abrirá cada obra en el navegador. Descarga el PDF o EPUB en {DOWNLOADS_FOLDER}")
    print("y vuelve aquí para seguir con la siguiente.\n")
    done = 0
    for number, paper in enumerate(papers, start=1):
        print(f"[{number}/{len(papers)}] {paper.title} ({paper.year or 's. f.'})")
        started = time.time()
        webbrowser.open(work_page(paper))

        while True:
            answer = questionary.select(
                "¿Lo has descargado?",
                choices=[
                    questionary.Choice("Sí, ya está en Descargas", value="done"),
                    questionary.Choice("Abrir otra vez la página", value="again"),
                    questionary.Choice("Saltar esta obra", value="skip"),
                    questionary.Choice("Terminar", value="stop"),
                ],
            ).ask()
            if answer == "again":
                webbrowser.open(work_page(paper))
                continue
            if answer in ("skip", None):
                break
            if answer == "stop":
                return done

            new_file = newest_download(started)
            if new_file is None:
                print(f"  No hay ningún PDF ni EPUB nuevo en {DOWNLOADS_FOLDER}.")
                continue
            file_path = file_away(new_file, paper, folder)
            print(f"  ✓ Guardado como {file_path.name}")
            done += 1
            break
    return done


def work_page(paper: Paper) -> str:
    # The DOI link takes to the publisher's page; without it, a found link or a search.
    if paper.doi:
        return f"https://doi.org/{paper.doi}"
    if paper.pdf_urls:
        return paper.pdf_urls[0]
    authors = " ".join(paper.authors[:1])
    return f"https://scholar.google.com/scholar?q={quote_plus(f'{paper.title} {authors}')}"


def newest_download(since: float) -> Path | None:
    """The newest complete PDF or EPUB saved in the Downloads folder after `since`."""
    candidates = [
        path for path in DOWNLOADS_FOLDER.iterdir()
        if path.is_file()
        and path.suffix.lower() not in PARTIAL_SUFFIXES
        and path.stat().st_mtime >= since - 1
    ]
    for path in sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True):
        with path.open("rb") as file:
            if file_extension(file.read(100)):
                return path
    return None


def file_away(downloaded: Path, paper: Paper, folder: Path) -> Path:
    with downloaded.open("rb") as file:
        extension = file_extension(file.read(100))
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / build_filename(paper, extension)
    shutil.move(downloaded, file_path)
    add_metadata(file_path, paper)
    return file_path
