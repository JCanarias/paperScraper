"""Finding an author's or a title's works in OpenAlex and the libraries, downloading their files and saving the lists.

The menu (main.py), the web panel (webapp/jobs.py), the daily check and the reviews all use it; nothing here
asks the user anything, except `download_author_works`, which can ask about the doubtful works.
"""
import datetime as dt
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import browser_session
import calibre_sync
import download_history
import task_progress
from bibliography import find_works, read_references
from downloader import add_metadata, download_paper, downloaded_file, is_downloaded, tag_repeated_filenames
from duplicates import combine, merge_duplicates, shared_surname, title_words
from languages import keep_chosen_languages, paper_language_allowed, using_languages
from models import MAX_TITLE_LENGTH_SHOWN, Author, Paper
from pdf_finders.base import PdfFinder
from pdf_finders.core import CoreFinder
from pdf_finders.semantic_scholar import SemanticScholarFinder
from pdf_finders.sci_hub import SeleniumSciHubFinder
from pdf_finders.unpaywall import UnpaywallFinder
from reviews import ask_doubtful, doubtful, needs_review, set_pending
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
from sources.openalex import OpenAlexSource
from sources.philarchive import PhilArchiveSource
from sources.wikimedia_commons import WikimediaCommonsSource
from sources.wikisource import WikisourceSource
from storage import (LIBRARY_FOLDER, find_saved_lists, load_content, load_papers, save_papers, save_search,
                     update_papers, work_key)

TITLE_SEARCH_FOLDER = LIBRARY_FOLDER / "Búsquedas por título"
BIBLIOGRAPHY_FOLDER = LIBRARY_FOLDER / "Bibliografías"
MAX_BOOKS_PER_SOURCE = 50
MAX_TITLE_RESULTS = 1000
# Fast APIs first; Sci-Hub opens a browser and is the slowest, so it only gets what is still missing.
PDF_FINDERS = [
    UnpaywallFinder(),
    SemanticScholarFinder(),
    CoreFinder(),
    SeleniumSciHubFinder(),
]
# Sci-Hub takes a few seconds per DOI and almost never gets a paper it didn't have before (1.766 DOIs
# and no new file on 2026-11-10): a work it couldn't give waits this long before it's asked again.
FINDER_RETRY_DAYS = {"SeleniumSciHubFinder": 30}
# Downloads that take longer than this say so in the log.
SLOW_DOWNLOAD_SECONDS = 10
# OpenAlex already gives the academic books; these add whole books, mostly public domain classics.
INTERNET_ARCHIVE = InternetArchiveSource()
# Classics in the public domain, first in Spanish; slower (15-30 s per author).
WIKISOURCE = WikisourceSource()
# DOAB, Dialnet and PhilArchive are searched in local copies of their catalogues (update_indexes.py).
BOOK_SOURCES: list[BookSource] = [
    INTERNET_ARCHIVE, GutenbergSource(), WIKISOURCE,
    # Scanned books in PDF (public domain), checked against the author each file names.
    WikimediaCommonsSource(),
    DoabSource(), DialnetSource(), PhilArchiveSource(),
    # Cervantes, the BNE, HathiTrust and Gallica go through a browser (browser_session.py).
    CervantesSource(), BNESource(), HathiTrustSource(), GallicaSource(),
]
# These need a free key in .env (EUROPEANA_API_KEY, GOOGLE_BOOKS_API_KEY).
BOOK_SOURCES.extend(source for source in (EuropeanaSource(), GoogleBooksSource()) if source.available)
# Libraries that didn't answer in this run; they are not asked again until the program restarts.
UNREACHABLE_SOURCES: set[str] = set()
# Catalogues kept in the local index, and how many of their works are compared with each pending one.
INDEXED_SOURCE_TYPES = (DoabSource, DialnetSource, PhilArchiveSource, BNESource)
MAX_CATALOGUE_CANDIDATES = 5
# Called with (paper, folder) every time a work is downloaded: the history of the web panel, and the
# daily check adds its own (Calibre and a Telegram message).
DOWNLOAD_LISTENERS: list[Callable[[Paper, Path], None]] = [download_history.record]


def find_and_download_pdfs(papers: list[Paper], folder: Path) -> None:
    # First the links the search already gave us, so the finders only look for what is still missing.
    with_links = [paper for paper in papers if paper.pdf_urls and not is_downloaded(paper, folder)]
    task_progress.works(sum(not is_downloaded(paper, folder) for paper in papers))
    try:
        find_and_download(papers, folder, with_links)
    finally:
        task_progress.not_found([paper.title for paper in papers if not is_downloaded(paper, folder)])


def find_and_download(papers: list[Paper], folder: Path, with_links: list[Paper]) -> None:
    if with_links:
        download_known_links(with_links, folder)
    for finder in PDF_FINDERS:
        pending = [paper for paper in papers if not is_downloaded(paper, folder)]
        if not pending:
            break
        if type(finder).__name__ in UNREACHABLE_SOURCES:
            continue
        pending = not_missed_recently(type(finder).__name__, pending)
        if pending:
            download_finder_links(finder, pending, folder)


def download_known_links(with_links: list[Paper], folder: Path) -> None:
    print(f"Descargando {len(with_links)} obras con enlace ya conocido...")
    task_progress.step(f"Descargando {len(with_links)} obras con enlace ya conocido")
    started = time.monotonic()
    for paper in with_links:
        try_download(paper, folder, paper.pdf_urls)
    print(f"Enlaces ya conocidos: {len(with_links)} obras en {time.monotonic() - started:.0f} s")


def not_missed_recently(finder_name: str, pending: list[Paper]) -> list[Paper]:
    """The works the finder hasn't looked for in vain lately (only the slow ones wait: FINDER_RETRY_DAYS)."""
    retry_days = FINDER_RETRY_DAYS.get(finder_name)
    if not retry_days:
        return pending
    ready = [paper for paper in pending if not missed_recently(paper, finder_name, retry_days)]
    if len(ready) < len(pending):
        print(f"{finder_name}: {len(pending) - len(ready)} obras esperan "
              f"(ya las buscó hace menos de {retry_days} días)")
    return ready


def download_finder_links(finder: PdfFinder, pending: list[Paper], folder: Path) -> None:
    """Ask the finder for links to the works' files, and download the new ones."""
    finder_name = type(finder).__name__
    task_progress.finder_step(finder)
    started = time.monotonic()
    try:
        found_urls = finder.find_pdf_urls(pending)
    except Exception as error:
        # A service that is down or refusing us (CORE timeouts, Semantic Scholar's limits)
        # would make every following search wait again, so it is skipped until the restart.
        UNREACHABLE_SOURCES.add(finder_name)
        print(f"Aviso: {finder_name} ha fallado y se salta en el resto de búsquedas: {error}")
        return
    print(f"{finder_name}: {len(pending)} obras en {time.monotonic() - started:.0f} s")

    today = dt.date.today().isoformat()
    for position, paper in enumerate(pending):
        new_urls = [url for url in found_urls.get(position, []) if url not in paper.pdf_urls]
        if new_urls:
            paper.pdf_urls.extend(new_urls)
            try_download(paper, folder, new_urls)
        # Giving only links that were already known doesn't count as finding it.
        if finder_name in FINDER_RETRY_DAYS and not is_downloaded(paper, folder):
            paper.finder_misses[finder_name] = today


def missed_recently(paper: Paper, finder_name: str, days: int) -> bool:
    try:
        missed = dt.date.fromisoformat(paper.finder_misses.get(finder_name, ""))
    except ValueError:
        return False
    return dt.date.today() < missed + dt.timedelta(days=days)


def try_download(paper: Paper, folder: Path, urls: list[str]) -> None:
    print(f"  Descargando {paper.doi or paper.title[:MAX_TITLE_LENGTH_SHOWN]}...", end=" ", flush=True)
    task_progress.trying(paper.title)
    started = time.monotonic()
    downloaded = download_paper(paper, folder, urls)
    seconds = time.monotonic() - started
    # Only the slow ones say how long they took (the browser, Gallica's pages, links that time out).
    print(("✓" if downloaded else "✗") + (f" ({seconds:.0f} s)" if seconds >= SLOW_DOWNLOAD_SECONDS else ""))
    if downloaded:
        for listener in DOWNLOAD_LISTENERS:
            try:
                listener(paper, folder)
            except Exception as error:
                print(f"  Aviso: {error}")


def author_folder(author: Author) -> Path:
    # Two different authors can have the same name, so we add their id to the folder name.
    short_id = author.id.split("/")[-1]
    return LIBRARY_FOLDER / f"{author.name} ({short_id})"


def search_folder(base_folder: Path, words: str) -> Path:
    # Remove characters that are not allowed in folder names.
    safe_words = re.sub(r'[<>:"/\\|?*\n\r\t]', "", words).strip()
    return base_folder / safe_words


def quit_finder_drivers() -> None:
    browser_session.quit_browser()
    for finder in PDF_FINDERS:
        finder.close()


def find_books(search: Callable[[BookSource], list[Paper]]) -> list[Paper]:
    """Every library at the same time, except the ones that share the browser, which go one after another.
    What each one found is shown afterwards, in the usual order, with the seconds it took."""
    book_sources = [source for source in BOOK_SOURCES if source.name not in UNREACHABLE_SOURCES]
    task_progress.step(f"Buscando libros en {len(book_sources)} bibliotecas")
    lanes = [[source] for source in book_sources if not source.uses_browser]
    lanes.append([source for source in book_sources if source.uses_browser])
    outcomes: dict[str, tuple[list[Paper] | Exception, float]] = {}

    def search_lane(lane: list[BookSource]) -> None:
        for book_source in lane:
            started = time.monotonic()
            try:
                outcomes[book_source.name] = search(book_source), time.monotonic() - started
            except Exception as error:
                outcomes[book_source.name] = error, time.monotonic() - started

    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        list(pool.map(search_lane, lanes))

    books = []
    for book_source in book_sources:
        found, seconds = outcomes[book_source.name]
        print(f"Buscando libros en {book_source.name}...", end=" ")
        if isinstance(found, requests.RequestException):
            # A library that doesn't answer (Gutendex is often overloaded) would make
            # every following search wait again, so it is skipped until the program restarts.
            UNREACHABLE_SOURCES.add(book_source.name)
            print(f"no responde; se salta en el resto de búsquedas ({type(found).__name__})")
        elif isinstance(found, browser_session.BrowserError):
            # A library that blocks the browser (HathiTrust, 2026-11-20) keeps blocking it for a while,
            # and each attempt costs about 20 s.
            UNREACHABLE_SOURCES.add(book_source.name)
            print(f"ha fallado ({found}); se salta en el resto de búsquedas")
        elif isinstance(found, Exception):
            print(f"ha fallado ({found})")
        else:
            print(f"{len(found)} ({seconds:.0f} s)")
            books.extend(found)
    return books


def find_by_title(source: OpenAlexSource, words: str) -> list[Paper]:
    """The works with these words in the title, ready to choose (the web panel uses it too)."""
    print("Buscando en OpenAlex...")
    papers, total = source.search_papers_by_title(words, MAX_TITLE_RESULTS)
    books = find_books(lambda book_source: book_source.search_books_by_title(words, MAX_BOOKS_PER_SOURCE))
    if not papers and not books:
        print("No se ha encontrado ninguna obra con esas palabras en el título.")
        return []

    if total > len(papers):
        print(f"\nHay {total} coincidencias en OpenAlex; se usan las {len(papers)} más relevantes.")
    print(f"\nSe han encontrado {len(papers)} obras en OpenAlex y {len(books)} libros en otras bibliotecas.\n")

    return prepare_list(papers + books)


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


def download_author_works(source: OpenAlexSource, selected_authors: list[Author], main_author: Author,
                          folder: Path, language_choice: dict, ask_doubtful_works: bool = True) -> None:
    """Find, download and save the works of one person. Without `ask_doubtful_works` (the web panel),
    the doubtful ones wait in "Revisar obras dudosas" instead of being asked here."""
    print(f"\n{'='*60}")
    print(f"Procesando: {', '.join(author.name for author in selected_authors)}")
    task_progress.group(main_author.name)
    print(f"{'='*60}")

    papers = prepare_list(find_author_works(source, selected_authors))
    if not papers:
        return
    keep_earlier_wanted(papers, folder)

    # Everything that isn't in Calibre yet is downloaded (but what the user rejected), the doubtful
    # works only if the user ticks them; the list keeps every work found.
    candidates = [paper for paper in papers if not paper.in_calibre and paper.review != "rejected"]
    decide_doubtful_works(candidates, main_author.name, ask_doubtful_works)
    to_download = [paper for paper in candidates if not doubtful(paper) or paper.review == "accepted"]
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
        papers_file = save_papers(main_author, papers, folder, selected_authors, language_choice)
        print(f"✓ Lista guardada en {papers_file}\n")


def decide_doubtful_works(candidates: list[Paper], author_name: str, ask_now: bool) -> None:
    """Ask which doubtful works are the author's. Without `ask_now`, or with Ctrl+C, they wait in
    "Revisar obras dudosas" (and are asked by Telegram, if the author is followed)."""
    waiting = [paper for paper in candidates if doubtful(paper) and paper.review != "accepted"]
    if not waiting:
        return
    print(f"\n{len(waiting)} obras solo están en Internet Archive o Google Books.")
    chosen = ask_doubtful(waiting, author_name) if ask_now else None
    if chosen is None:
        print("Se quedan en \"Revisar obras dudosas\" hasta que digas cuáles son suyas.")
        for paper in waiting:
            set_pending(paper)
        return
    for paper in waiting:
        paper.review = "accepted" if any(paper is one for one in chosen) else "rejected"


def find_author_works(source: OpenAlexSource, profiles: list[Author]) -> list[Paper]:
    """Every work of these OpenAlex profiles (one person), and the books under their names."""
    papers: list[Paper] = []
    task_progress.step("Buscando sus obras en OpenAlex")
    started = time.monotonic()
    for author in profiles:
        papers += source.get_papers(author)
    openalex_count = len(papers)
    print(f"OpenAlex: {openalex_count} obras ({time.monotonic() - started:.0f} s)")
    for name in dict.fromkeys(author.name for author in profiles):
        papers += find_books(lambda book_source: book_source.search_books_by_author(name, MAX_BOOKS_PER_SOURCE))
    print(f"\nSe han encontrado {openalex_count} obras en OpenAlex y "
          f"{len(papers) - openalex_count} en otras bibliotecas.")
    return papers


def prepare_list(papers: list[Paper], only_chosen_languages: bool = True) -> list[Paper]:
    """Join the repeated works, mark the ones already in Calibre and give each one its own file name.

    The works in languages not chosen in "Idiomas" are left out, unless `only_chosen_languages` is False.
    """
    papers = merge_duplicates(papers)
    if only_chosen_languages:
        papers = keep_chosen_languages(papers)
    in_calibre = calibre_sync.mark_papers(papers)
    if in_calibre:
        print(f"{in_calibre} ya están en Calibre.")
        if calibre_sync.connected_library.deleted_by_user:
            print(f"De ellas, {calibre_sync.connected_library.deleted_by_user} las borraste de Calibre: no se descargan.")
    tag_repeated_filenames(papers)
    return papers


def keep_earlier_wanted(papers: list[Paper], folder: Path) -> None:
    # A new search of the same author replaces its list, but the works chosen before
    # must stay chosen, so "Reintentar las obras pendientes" still finds them.
    papers_file = folder / "papers.json"
    if not papers_file.exists():
        return
    earlier = load_papers(papers_file)
    wanted = {work_key(paper) for paper in earlier if paper.wanted}
    # The user's answers about doubtful works, and the works they don't want (rejected).
    reviews = {work_key(paper): (paper.review, paper.review_id) for paper in earlier if paper.review}
    # The ones sent to Calibre (and deleted here) must not be downloaded again.
    sent = {work_key(paper) for paper in earlier if paper.sent_to_calibre}
    for paper in papers:
        if work_key(paper) in wanted:
            paper.wanted = True
        if work_key(paper) in sent:
            paper.sent_to_calibre = paper.in_calibre = True
        if work_key(paper) in reviews:
            paper.review, paper.review_id = reviews[work_key(paper)]
            if paper.review in ("rejected", "pending"):
                paper.wanted = False


def after_download(papers: list[Paper], folder: Path) -> None:
    """Send the new files to Calibre and say how to get the ones still missing."""
    calibre_sync.upload_new_files(papers, folder)
    missing = sum(not is_downloaded(paper, folder) and not paper.in_calibre for paper in papers)
    if missing:
        print(f"{missing} obras quedan pendientes: se reintentarán con \"Reintentar las obras pendientes\","
              " y las que solo se pueden bajar desde el navegador, con \"Descargar a mano las pendientes\".")


def list_language_allowed(papers_file: Path, paper: Paper) -> bool:
    """Whether the work is in the languages of its list (the author's own, or the general ones)."""
    with using_languages(load_content(papers_file).get("language_choice")):
        return paper_language_allowed(paper)


def download_bibliography(source: OpenAlexSource, file_path: Path) -> None:
    """Find the works of a bibliography and download the ones not in Calibre (the web panel uses it too)."""
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

    # The bibliography is already a choice: every language, and everything not in Calibre is downloaded.
    papers = prepare_list(papers, only_chosen_languages=False)
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
        for catalogue in list(catalogues):
            try:
                add_copies_from(catalogue, paper)
            except Exception as error:
                print(f"Aviso: no se ha podido buscar en el catálogo local de {catalogue.name}: {error}")
                catalogues.remove(catalogue)
        improved += len(paper.pdf_urls) > links_before
    return improved


def add_copies_from(catalogue: BookSource, paper: Paper) -> None:
    # The subtitle is often written differently (or missing) in each catalogue.
    main_title = paper.title.split(":")[0]
    for candidate in catalogue.search_books_by_title(main_title, MAX_CATALOGUE_CANDIDATES):
        if same_main_work(paper, candidate):
            combine(paper, candidate)


def add_openalex_links(papers: list[Paper]) -> int:
    """Add to each work the links OpenAlex knows today (new open copies, and the pages of the open copies,
    which searches made before didn't keep). Return how many works got new links."""
    by_id = {paper.identifiers["openalex"]: paper for paper in papers if paper.identifiers.get("openalex")}
    if not by_id:
        return 0
    try:
        current = OpenAlexSource().get_papers_by_openalex_ids(list(by_id))
    except Exception as error:
        print(f"Aviso: no se han podido actualizar los enlaces de OpenAlex: {error}")
        return 0
    improved = 0
    for fresh in current:
        paper = by_id.get(fresh.identifiers.get("openalex"))
        new_urls = [url for url in fresh.pdf_urls if paper and url not in paper.pdf_urls]
        if new_urls:
            paper.pdf_urls.extend(new_urls)
            improved += 1
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
        calibre_sync.mark_papers(papers)
        pending = [paper for paper in papers
                   if paper.wanted and not paper.in_calibre and not is_downloaded(paper, folder)
                   and list_language_allowed(papers_file, paper) and not needs_review(paper, folder)]
        if not pending:
            continue

        print(f"\n{folder}: {len(pending)} pendientes")
        task_progress.group(folder.name)
        task_progress.step("Buscando copias en los catálogos locales y en OpenAlex")
        found = add_catalogue_copies(pending)
        if found:
            print(f"Encontradas en los catálogos locales: {found}")
        refreshed = add_openalex_links(pending)
        if refreshed:
            print(f"Con enlaces nuevos en OpenAlex: {refreshed}")
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
