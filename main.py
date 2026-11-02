import re
from collections.abc import Callable
from pathlib import Path

import questionary
import requests

from bibliography import find_works, read_references
from calibre_library import CalibreLibrary
from downloader import add_metadata, download_paper, downloaded_file, is_downloaded, tag_repeated_filenames
from duplicates import combine, merge_duplicates, shared_surname, title_words
from manual_download import download_by_hand
from models import Author, Paper
from pdf_finders.core import CoreFinder
from pdf_finders.custom_legal_source import CustomLegalSourceFinder
from pdf_finders.semantic_scholar import SemanticScholarFinder
from pdf_finders.selenium_fast import SeleniumSciHubFinder
from pdf_finders.unpaywall import UnpaywallFinder
from sources.base import BookSource
from sources.bne import BNESource
from sources.cervantes import CervantesSource
from sources.dialnet import DialnetSource
from sources.doab import DoabSource
from sources.europeana import EuropeanaSource
from sources.gallica import GallicaSource
from sources.google_books import GoogleBooksSource
from sources.gutenberg import GutenbergSource
from sources.hathitrust import HathiTrustSource
from sources.internet_archive import InternetArchiveSource
from sources.names import name_words
from sources.navarra import NavarraBooksSource
from sources.openalex import OpenAlexSource
from sources.philarchive import PhilArchiveSource
from sources.wikisource import WikisourceSource
from update_indexes import INDEXED_SOURCES, update_indexes
from storage import find_saved_lists, load_papers, save_papers, save_search, update_papers

LIBRARY_FOLDER = Path("library")
TITLE_SEARCH_FOLDER = LIBRARY_FOLDER / "Búsquedas por título"
BIBLIOGRAPHY_FOLDER = LIBRARY_FOLDER / "Bibliografías"
MAX_BOOKS_PER_SOURCE = 50
MAX_TITLE_RESULTS = 1000
MAX_AUTHORS_SHOWN = 3
# How many works of each author are shown before choosing which author to download.
MAX_PREVIEW_PAPERS = 15
MAX_TITLE_LENGTH_SHOWN = 100
# Fast APIs first; Sci-Hub opens a browser and is the slowest, so it only gets what is still missing.
PDF_FINDERS = [
    UnpaywallFinder(),
    SemanticScholarFinder(),
    CoreFinder(),
    SeleniumSciHubFinder(),
    CustomLegalSourceFinder(),
]
# OpenAlex already gives the academic books; these add whole books, mostly public domain classics.
INTERNET_ARCHIVE = InternetArchiveSource()
# Classics in the public domain, first in Spanish; slower (15-30 s per author).
WIKISOURCE = WikisourceSource()
# DOAB, Dialnet and PhilArchive are searched in local copies of their catalogues (update_indexes.py).
BOOK_SOURCES: list[BookSource] = [
    INTERNET_ARCHIVE, GutenbergSource(), WIKISOURCE, DoabSource(), DialnetSource(), PhilArchiveSource(),
    CervantesSource(), BNESource(), NavarraBooksSource(),
    GoogleBooksSource(), HathiTrustSource(), GallicaSource(),
]
# Optional sources requiring API keys
europeana = EuropeanaSource()
if europeana.available:
    BOOK_SOURCES.append(europeana)
# Libraries that didn't answer in this run; they are not asked again until the program restarts.
UNREACHABLE_SOURCES: set[str] = set()
# Catalogues kept in the local index, and how many of their works are compared with each pending one.
INDEXED_SOURCE_TYPES = (DoabSource, DialnetSource, PhilArchiveSource)
MAX_CATALOGUE_CANDIDATES = 5
# The user's Calibre library, when .env has its address; set in main().
calibre: CalibreLibrary | None = None


def author_label(author: Author) -> str:
    institutions = ", ".join(author.institutions) or "institución desconocida"
    return f"{author.name} ({author.works_count} obras) - {institutions}"


def choose_authors(source: OpenAlexSource, authors: list[Author]) -> list[Author]:
    if len(authors) == 1:
        return authors

    print("\nVarios autores coinciden con ese nombre.")
    # The user can look at the works of each author as many times as needed before choosing.
    while True:
        choice = questionary.select(
            "Elige un autor para ver sus obras:",
            choices=[
                *(questionary.Choice(author_label(author), value=author) for author in authors),
                questionary.Separator(),
                questionary.Choice("→ Elegir de qué autores descargar", value="choose"),
                questionary.Choice("Cancelar", value="cancel"),
            ],
        ).ask()

        # ask() returns None when the user presses Ctrl+C.
        if choice is None or choice == "cancel":
            return []
        if choice == "choose":
            break
        preview_author(source, choice)

    selected = questionary.checkbox(
        "Marca los autores cuyas obras quieres descargar:",
        choices=[questionary.Choice(author_label(author), value=author) for author in authors],
        instruction="\n  ↑/↓ moverse · Espacio marcar · Enter confirmar",
    ).ask()
    return selected or []


def preview_author(source: OpenAlexSource, author: Author) -> None:
    papers = source.get_top_papers(author, MAX_PREVIEW_PAPERS)
    print(f"\n{author_label(author)}")
    print(f"Sus {len(papers)} obras más citadas:\n")
    for paper in papers:
        journal = f" · {paper.journal}" if paper.journal else ""
        print(f"  {paper_label(paper)}{journal}")
    if author.works_count > len(papers):
        print(f"  … y {author.works_count - len(papers)} más.")
    print()


def short_authors(paper: Paper) -> str:
    if not paper.authors:
        return "autor desconocido"
    names = ", ".join(paper.authors[:MAX_AUTHORS_SHOWN])
    if len(paper.authors) > MAX_AUTHORS_SHOWN:
        names += " et al."
    return names


def paper_label(paper: Paper) -> str:
    title = paper.title or "(sin título)"
    if len(title) > MAX_TITLE_LENGTH_SHOWN:
        title = title[:MAX_TITLE_LENGTH_SHOWN - 1] + "…"
    # [PDF] means OpenAlex already knows a direct link; the PDF finders may still find others.
    pdf_mark = "  [PDF]" if paper.pdf_urls else ""
    source_mark = f"  ({paper.source})" if paper.source else ""
    calibre_mark = "  [En Calibre]" if paper.in_calibre else ""
    return f"{paper.year or '----'} · {title} — {short_authors(paper)}{pdf_mark}{source_mark}{calibre_mark}"


def choose_papers_with_checkboxes(papers: list[Paper]) -> list[Paper]:
    # The list scrolls with the arrow keys, so it works with hundreds of results.
    # Typing filters the list by title, which helps to find a specific work.
    choices = [questionary.Choice(paper_label(paper), value=index) for index, paper in enumerate(papers)]
    selected_indexes = questionary.checkbox(
        "Marca las obras que quieres descargar:",
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction=(
            "\n  ↑/↓ moverse · Espacio marcar · Ctrl+A marcar/desmarcar todo · "
            "Tab invertir · escribe para filtrar · Enter confirmar"
        ),
    ).ask()

    # ask() returns None when the user presses Ctrl+C.
    if not selected_indexes:
        return []
    return [papers[index] for index in sorted(selected_indexes)]


def confirm_papers_to_download(papers: list[Paper]) -> list[Paper]:
    missing = [paper for paper in papers if not paper.in_calibre]
    if len(missing) < len(papers):
        print(f"{len(papers) - len(missing)} de estas obras ya están en Calibre.")
        choices = [
            questionary.Choice(f"Descargar las que no están en Calibre ({len(missing)})", value="missing"),
            questionary.Choice(f"Descargar todas ({len(papers)})", value="all"),
        ]
    else:
        choices = [questionary.Choice(f"Descargar todos ({len(papers)})", value="all")]
    choice = questionary.select(
        "¿Qué quieres hacer?",
        choices=[
            *choices,
            questionary.Choice("Elegir uno a uno", value="choose"),
            questionary.Choice("Cancelar", value="cancel"),
        ],
    ).ask()

    if choice == "missing":
        return missing
    if choice == "all":
        return papers
    if choice == "choose":
        return choose_papers_with_checkboxes(papers)
    return []


def find_and_download_pdfs(papers: list[Paper], folder: Path) -> None:
    # First the links the search already gave us, so the finders only look for what is still missing.
    with_links = [paper for paper in papers if paper.pdf_urls and not is_downloaded(paper, folder)]
    if with_links:
        print(f"Descargando {len(with_links)} obras con enlace ya conocido...")
        for paper in with_links:
            try_download(paper, folder, paper.pdf_urls)

    for finder in PDF_FINDERS:
        pending = [paper for paper in papers if not is_downloaded(paper, folder)]
        if not pending:
            break
        if type(finder).__name__ in UNREACHABLE_SOURCES:
            continue

        try:
            found_urls = finder.find_pdf_urls(pending)
        except Exception as error:
            # A service that is down or refusing us (CORE timeouts, Semantic Scholar's limits)
            # would make every following search wait again, so it is skipped until the restart.
            UNREACHABLE_SOURCES.add(type(finder).__name__)
            print(f"Aviso: {type(finder).__name__} ha fallado y se salta en el resto de búsquedas: {error}")
            continue

        for position, urls in found_urls.items():
            paper = pending[position]
            new_urls = [url for url in urls if url not in paper.pdf_urls]
            if new_urls:
                paper.pdf_urls.extend(new_urls)
                try_download(paper, folder, new_urls)


def try_download(paper: Paper, folder: Path, urls: list[str]) -> None:
    print(f"  Descargando {paper.doi or paper.title[:MAX_TITLE_LENGTH_SHOWN]}...", end=" ", flush=True)
    print("✓" if download_paper(paper, folder, urls) else "✗")


def author_folder(author: Author) -> Path:
    # Two different authors can have the same name, so we add their id to the folder name.
    short_id = author.id.split("/")[-1]
    return LIBRARY_FOLDER / f"{author.name} ({short_id})"


def search_folder(base_folder: Path, words: str) -> Path:
    # Remove characters that are not allowed in folder names.
    safe_words = re.sub(r'[<>:"/\\|?*\n\r\t]', "", words).strip()
    return base_folder / safe_words


def quit_finder_drivers() -> None:
    for finder in PDF_FINDERS:
        if hasattr(finder, 'driver') and finder.driver:
            try:
                finder.driver.quit()
            except:
                pass


def find_books(search: Callable[[BookSource], list[Paper]]) -> list[Paper]:
    books = []
    for book_source in BOOK_SOURCES:
        if book_source.name in UNREACHABLE_SOURCES:
            continue
        print(f"Buscando libros en {book_source.name}...", end=" ", flush=True)
        try:
            found = search(book_source)
        except requests.RequestException as error:
            # A library that doesn't answer (Gutendex is often overloaded) would make
            # every following search wait again, so it is skipped until the program restarts.
            UNREACHABLE_SOURCES.add(book_source.name)
            print(f"no responde; se salta en el resto de búsquedas ({type(error).__name__})")
            continue
        except Exception as error:
            print(f"ha fallado ({error})")
            continue
        print(len(found))
        books.extend(found)
    return books


def search_by_title(source: OpenAlexSource) -> None:
    words = input("Palabras del título: ").strip()
    if not words:
        print("No has escrito ninguna palabra.")
        return

    print("Buscando en OpenAlex...")
    papers, total = source.search_papers_by_title(words, MAX_TITLE_RESULTS)
    books = find_books(lambda book_source: book_source.search_books_by_title(words, MAX_BOOKS_PER_SOURCE))
    if not papers and not books:
        print("No se ha encontrado ninguna obra con esas palabras en el título.")
        return

    if total > len(papers):
        print(f"\nHay {total} coincidencias en OpenAlex; se usan las {len(papers)} más relevantes.")
    print(f"\nSe han encontrado {len(papers)} obras en OpenAlex y {len(books)} libros en otras bibliotecas.\n")

    found = prepare_list(papers + books)
    selected_papers = confirm_papers_to_download(found)
    if not selected_papers:
        print("No se descarga nada.")
        return

    download_and_save_search(words, selected_papers, search_folder(TITLE_SEARCH_FOLDER, words))


def download_and_save_search(words: str, selected_papers: list[Paper], folder: Path) -> None:
    for paper in selected_papers:
        paper.wanted = True
    try:
        print(f"\nBuscando y descargando ({len(selected_papers)} obras)...")
        find_and_download_pdfs(selected_papers, folder)
    except KeyboardInterrupt:
        print("\n\n⏹ Búsqueda interrumpida por el usuario")
        quit_finder_drivers()
        return

    print_download_summary(selected_papers, folder)
    after_download(selected_papers, folder)
    for paper in selected_papers:
        paper.downloaded = is_downloaded(paper, folder)

    papers_file = save_search(words, selected_papers, folder)
    print(f"✓ Lista guardada en {papers_file}\n")


def print_download_summary(papers: list[Paper], folder: Path) -> None:
    not_found = [paper for paper in papers if not is_downloaded(paper, folder)]
    print(f"\n✓ Descargados {len(papers) - len(not_found)}/{len(papers)} en {folder}")
    if not_found:
        print("Sin archivo:")
        for paper in not_found:
            print(f"  - {paper.title} ({paper.year or 's. f.'})")


def search_by_author(source: OpenAlexSource) -> None:
    name = input("Nombre del autor: ")
    authors = source.find_authors(name)
    if not authors:
        print("No se ha encontrado ningún autor con ese nombre.")
        return

    selected_authors = choose_authors(source, authors)
    if not selected_authors:
        print("No se descarga nada.")
        return

    # OpenAlex often splits one person into several profiles ("Lourdes Flamarique",
    # "L. Flamarique-Zaratiegui"...), so the chosen ones become a single list and folder,
    # named after the profile with most works.
    main_author = max(selected_authors, key=lambda author: author.works_count)
    print(f"\n{'='*60}")
    print(f"Procesando: {', '.join(author.name for author in selected_authors)}")
    print(f"{'='*60}")

    papers: list[Paper] = []
    for author in selected_authors:
        papers += source.get_papers(author)
    openalex_count = len(papers)
    for name in dict.fromkeys(author.name for author in selected_authors):
        papers += find_books(lambda book_source: book_source.search_books_by_author(name, MAX_BOOKS_PER_SOURCE))
    print(f"\nSe han encontrado {openalex_count} obras en OpenAlex y "
          f"{len(papers) - openalex_count} en otras bibliotecas.")
    papers = prepare_list(papers)
    if not papers:
        return
    folder = author_folder(main_author)
    keep_earlier_wanted(papers, folder)

    # Everything that isn't in Calibre yet is downloaded; the list keeps every work found.
    to_download = [paper for paper in papers if not paper.in_calibre]
    for paper in to_download:
        paper.wanted = True
    try:
        print(f"\nBuscando y descargando {len(to_download)} obras de {len(papers)}...")
        find_and_download_pdfs(to_download, folder)
    except KeyboardInterrupt:
        print("\n\n⏹ Búsqueda interrumpida por el usuario")
        quit_finder_drivers()
    finally:
        print_download_summary(to_download, folder)
        after_download(to_download, folder)
        for paper in papers:
            paper.downloaded = is_downloaded(paper, folder)
        papers_file = save_papers(main_author, papers, folder)
        print(f"✓ Lista guardada en {papers_file}\n")


def prepare_list(papers: list[Paper]) -> list[Paper]:
    """Join the repeated works, mark the ones already in Calibre and give each one its own file name."""
    papers = merge_duplicates(papers)
    if calibre:
        in_calibre = calibre.mark_papers(papers)
        if in_calibre:
            print(f"{in_calibre} ya están en Calibre.")
    tag_repeated_filenames(papers)
    return papers


def keep_earlier_wanted(papers: list[Paper], folder: Path) -> None:
    # A new search of the same author replaces its list, but the works chosen before
    # must stay chosen, so "Reintentar las obras pendientes" still finds them.
    papers_file = folder / "papers.json"
    if not papers_file.exists():
        return
    wanted = {work_key(paper) for paper in load_papers(papers_file) if paper.wanted}
    for paper in papers:
        if work_key(paper) in wanted:
            paper.wanted = True


def work_key(paper: Paper) -> str:
    return (paper.doi or "").lower() or " ".join(name_words(paper.title or ""))


def after_download(papers: list[Paper], folder: Path) -> None:
    """Send the new files to Calibre and say how to get the ones still missing."""
    if calibre:
        new = [paper for paper in papers if not paper.in_calibre and is_downloaded(paper, folder)]
        if new:
            print(f"\nSubiendo a Calibre {len(new)} archivos nuevos...")
            upload_files(new, folder)
    missing = sum(not is_downloaded(paper, folder) for paper in papers)
    if missing:
        print(f"{missing} obras quedan pendientes: se reintentarán con \"Reintentar las obras pendientes\","
              " y las que solo se pueden bajar desde el navegador, con \"Descargar a mano las pendientes\".")


def download_pending_by_hand() -> None:
    """Open in the browser, one by one, the chosen works that still have no file."""
    for papers_file in find_saved_lists(LIBRARY_FOLDER):
        folder = papers_file.parent
        papers = load_papers(papers_file)
        if calibre:
            calibre.mark_papers(papers)
        pending = [paper for paper in papers
                   if paper.wanted and not paper.in_calibre and not is_downloaded(paper, folder)]
        if not pending:
            continue
        print(f"\n{folder}: {len(pending)} pendientes")
        choice = questionary.select(
            "¿Qué hacer con esta carpeta?",
            choices=[
                questionary.Choice("Abrirlas en el navegador", value="open"),
                questionary.Choice("Pasar a la siguiente carpeta", value="next"),
                questionary.Choice("Terminar", value="stop"),
            ],
        ).ask()
        if choice in ("stop", None):
            return
        if choice == "next":
            continue
        download_by_hand(pending, folder)
        after_download(pending, folder)
        for paper in papers:
            paper.downloaded = is_downloaded(paper, folder)
        update_papers(papers_file, papers)


def upload_files(papers: list[Paper], folder: Path) -> None:
    uploaded = 0
    for paper in papers:
        print(f"  Subiendo {paper.title[:MAX_TITLE_LENGTH_SHOWN]}...", end=" ", flush=True)
        try:
            if calibre.upload(downloaded_file(paper, folder), paper):
                uploaded += 1
                print("✓")
            else:
                print("ya estaba")
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 403:
                print("\nEl usuario de Calibre no tiene permiso para añadir libros (es de solo lectura).")
                return
            print(f"✗ ({error})")
        except Exception as error:
            print(f"✗ ({error})")
    print(f"✓ Subidos a Calibre: {uploaded}/{len(papers)}")


def search_by_bibliography(source: OpenAlexSource) -> None:
    path_text = questionary.path("Archivo de la bibliografía (.bib, .ris o .txt con una referencia por línea):").ask()
    if not path_text:
        return
    file_path = Path(path_text.strip().strip('"'))
    if not file_path.is_file():
        print(f"No existe el archivo {file_path}.")
        return

    references = read_references(file_path)
    if not references:
        print("No se ha encontrado ninguna referencia en el archivo.")
        return
    print(f"\nBuscando {len(references)} referencias...")
    papers, missing = find_works(references, source, INTERNET_ARCHIVE)
    if missing:
        print(f"\nNo se han encontrado {len(missing)} referencias:")
        for reference in missing:
            print(f"  - {reference.text[:MAX_TITLE_LENGTH_SHOWN]}")
    if not papers:
        return

    papers = prepare_list(papers)
    # The bibliography is already a choice, so everything not in Calibre is downloaded.
    selected_papers = [paper for paper in papers if not paper.in_calibre]
    print(f"\nSe han encontrado {len(papers)} obras; se descargan las {len(selected_papers)} que no están en Calibre.")
    download_and_save_search(f"Bibliografía: {file_path.name}", selected_papers,
                             search_folder(BIBLIOGRAPHY_FOLDER, file_path.stem))


def add_catalogue_copies(papers: list[Paper]) -> int:
    """Add to each work the links of its copies in the local catalogues (DOAB, Dialnet, PhilArchive).

    Those catalogues grow after every harvest, so a work that had no file before may have one now.
    Return how many works got new links.
    """
    catalogues = [source for source in BOOK_SOURCES
                  if isinstance(source, INDEXED_SOURCE_TYPES) and source.index.count() > 0]
    improved = 0
    for paper in papers:
        if not paper.title:
            continue
        links_before = len(paper.pdf_urls)
        # The subtitle is often written differently (or missing) in each catalogue.
        main_title = paper.title.split(":")[0]
        for catalogue in catalogues:
            try:
                candidates = catalogue.search_books_by_title(main_title, MAX_CATALOGUE_CANDIDATES)
            except Exception:
                continue
            for candidate in candidates:
                if same_main_work(paper, candidate):
                    combine(paper, candidate)
        improved += len(paper.pdf_urls) > links_before
    return improved


def same_main_work(paper: Paper, candidate: Paper) -> bool:
    if title_words(paper.title.split(":")[0]) != title_words((candidate.title or "").split(":")[0]):
        return False
    if paper.year and candidate.year and abs(paper.year - candidate.year) > 2:
        return False
    return shared_surname(paper.authors, candidate.authors)


def retry_pending() -> None:
    """Look again for the works chosen in earlier searches that still have no file."""
    for papers_file in find_saved_lists(LIBRARY_FOLDER):
        folder = papers_file.parent
        papers = load_papers(papers_file)
        if calibre:
            calibre.mark_papers(papers)
        pending = [paper for paper in papers
                   if paper.wanted and not paper.in_calibre and not is_downloaded(paper, folder)]
        if not pending:
            continue

        print(f"\n{folder}: {len(pending)} pendientes")
        found = add_catalogue_copies(pending)
        if found:
            print(f"Encontradas en los catálogos locales: {found}")
        try:
            find_and_download_pdfs(pending, folder)
        except KeyboardInterrupt:
            print("\n\n⏹ Búsqueda interrumpida por el usuario")
            quit_finder_drivers()
            return
        print_download_summary(pending, folder)
        after_download(pending, folder)
        for paper in papers:
            paper.downloaded = is_downloaded(paper, folder)
        update_papers(papers_file, papers)
    print("\n✓ Pendientes revisadas.")


def upload_downloaded() -> None:
    if not calibre:
        print("No hay ninguna biblioteca de Calibre configurada (CALIBRE_URL en .env).")
        return
    anything_new = False
    for papers_file in find_saved_lists(LIBRARY_FOLDER):
        folder = papers_file.parent
        papers = load_papers(papers_file)
        calibre.mark_papers(papers)
        new = [paper for paper in papers if not paper.in_calibre and is_downloaded(paper, folder)]
        if new:
            anything_new = True
            print(f"\n{folder}: {len(new)} archivos que no están en Calibre")
            upload_files(new, folder)
            update_papers(papers_file, papers)
    if not anything_new:
        print("✓ Todo lo descargado ya está en Calibre.")


def complete_details(source: OpenAlexSource, papers: list[Paper]) -> list[Paper]:
    # Lists saved before the metadata existed only have title, year, DOI and authors,
    # so we ask OpenAlex again for the rest. We keep the PDF links and download state we had.
    dois = [paper.doi for paper in papers if paper.doi]
    found = {paper.doi.lower(): paper for paper in source.get_papers_by_dois(dois)}

    completed = []
    for paper in papers:
        new_paper = found.get(paper.doi.lower()) if paper.doi else None
        if new_paper:
            # Keep the saved title and year: the PDF file name was built from them.
            new_paper.title = paper.title
            new_paper.year = paper.year
            new_paper.pdf_urls = paper.pdf_urls
            new_paper.downloaded = paper.downloaded
            completed.append(new_paper)
        else:
            completed.append(paper)
    return completed


def tag_downloaded_files(source: OpenAlexSource) -> None:
    lists = find_saved_lists(LIBRARY_FOLDER)
    if not lists:
        print(f"No hay ninguna lista guardada en {LIBRARY_FOLDER}.")
        return

    for papers_file in lists:
        folder = papers_file.parent
        papers = load_papers(papers_file)
        downloaded = [paper for paper in papers if is_downloaded(paper, folder)]
        if not downloaded:
            continue

        print(f"\n{folder} ({len(downloaded)} archivos)")
        papers = complete_details(source, papers)
        tag_repeated_filenames(papers)
        update_papers(papers_file, papers)

        for paper in papers:
            if is_downloaded(paper, folder):
                print(f"  {paper.title}")
                add_metadata(downloaded_file(paper, folder), paper)

    print("\n✓ Metadatos escritos.")


def connect_calibre() -> None:
    global calibre
    calibre = CalibreLibrary.from_environment()
    if calibre is None:
        return
    try:
        print(f"Calibre: {calibre.load_index()} libros en la biblioteca.")
    except Exception as error:
        print(f"Aviso: no se puede leer la biblioteca de Calibre: {error}")
        calibre = None


def main() -> None:
    source = OpenAlexSource()
    connect_calibre()

    choice = questionary.select(
        "¿Cómo quieres buscar?",
        choices=[
            questionary.Choice("Por autor", value="author"),
            questionary.Choice("Por palabras del título", value="title"),
            questionary.Choice("Desde una bibliografía (BibTeX, RIS o texto)", value="bibliography"),
            questionary.Choice("Reintentar las obras pendientes", value="retry"),
            questionary.Choice("Descargar a mano las pendientes (en el navegador)", value="by_hand"),
            questionary.Choice("Subir a Calibre lo ya descargado", value="upload"),
            questionary.Choice("Actualizar los catálogos locales (Dialnet, PhilArchive, DOAB)", value="indexes"),
            questionary.Choice("Poner metadatos a los archivos ya descargados", value="tag"),
        ],
    ).ask()

    if choice == "author":
        search_by_author(source)
    elif choice == "title":
        search_by_title(source)
    elif choice == "bibliography":
        search_by_bibliography(source)
    elif choice == "retry":
        retry_pending()
    elif choice == "by_hand":
        download_pending_by_hand()
    elif choice == "upload":
        upload_downloaded()
    elif choice == "indexes":
        update_indexes(list(INDEXED_SOURCES))
    elif choice == "tag":
        tag_downloaded_files(source)


if __name__ == "__main__":
    main()
