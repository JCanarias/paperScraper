"""Daily check of the followed authors (menu: "Autores que seguir").

For each of them, as a new search by author would do, but without asking anything:
1. looks for works that weren't in its list yet (OpenAlex and the other libraries) and adds them;
   the ones not in Calibre are marked to download;
2. looks again for a file of every chosen work still without one (local catalogues and PDF finders);
   a work that keeps failing waits longer each time (1, 2, 4... up to 30 days), unless it gets new links;
3. sends every new file to Calibre and a Telegram message for each one.

The tower runs it every day at 6:00 (the "daily" container, tower/scheduler.py). By hand:
    docker compose exec daily python daily_check.py
"""
import datetime as dt
import sys
import traceback
from pathlib import Path

import main
from downloader import is_downloaded, tag_repeated_filenames
from duplicates import merge_duplicates, same_work
from languages import keep_chosen_languages, languages_label, paper_language_allowed, using_languages
from models import Paper
from run_lock import take_daily_lock
from sources.openalex import OpenAlexSource
from storage import author_profiles, find_saved_lists, load_content, load_papers, update_papers
from telegram_notify import send_message

# The longest wait between two searches for the file of a work that keeps failing.
MAX_DAYS_BETWEEN_CHECKS = 30


def followed_lists() -> list[Path]:
    return [papers_file for papers_file in find_saved_lists(main.LIBRARY_FOLDER)
            if load_content(papers_file).get("follow")]


def check_author(source: OpenAlexSource, papers_file: Path) -> None:
    folder = papers_file.parent
    content = load_content(papers_file)
    papers = load_papers(papers_file)
    print(f"\n{'=' * 60}\n{folder.name}\n{'=' * 60}")
    # The languages chosen when this author was searched (or the general ones).
    with using_languages(content.get("language_choice")):
        print(f"Idiomas: {languages_label()}")
        check_author_works(source, papers_file, content, papers)


def check_author_works(source: OpenAlexSource, papers_file: Path, content: dict, papers: list[Paper]) -> None:
    folder = papers_file.parent
    today = dt.date.today()
    # A work that gets new links today (a new copy found) is tried today, whatever it failed before.
    links_before = {id(paper): len(paper.pdf_urls) for paper in papers}
    try:
        found = keep_chosen_languages(merge_duplicates(main.find_author_works(source, author_profiles(content))))
    except Exception as error:
        # Without the new search, the pending works of the list are still looked for.
        print(f"Aviso: no se han podido buscar obras nuevas: {error}")
        found = []
    new = add_new_works(papers, found)
    if main.calibre:
        main.calibre.mark_papers(papers)
        removed = main.remove_files_in_calibre(papers, folder)
        if removed:
            print(f"Borrados {removed} archivos que ya están en Calibre")
    # As in a search by author: everything new that isn't in Calibre is downloaded.
    for paper in new:
        paper.wanted = not paper.in_calibre
    print(f"Obras nuevas: {len(new)}")

    pending = [paper for paper in papers
               if paper.wanted and not paper.in_calibre and not is_downloaded(paper, folder)
               and paper_language_allowed(paper)]
    try:
        if pending:
            found_in_catalogues = main.add_catalogue_copies(pending)
            if found_in_catalogues:
                print(f"Encontradas en los catálogos locales: {found_in_catalogues}")
        due = [paper for paper in pending
               if due_today(paper, today) or len(paper.pdf_urls) > links_before.get(id(paper), 0)]
        print(f"Pendientes de archivo: {len(pending)}; se buscan hoy {len(due)} "
              f"(las que fallaron hace poco esperan unos días)")
        if due:
            main.find_and_download_pdfs(due, folder)
            for paper in due:
                if not is_downloaded(paper, folder):
                    paper.failed_checks += 1
                    paper.last_check = today.isoformat()
    finally:
        for paper in papers:
            paper.downloaded = is_downloaded(paper, folder)
        update_papers(papers_file, papers)


def due_today(paper: Paper, today: dt.date) -> bool:
    """Whether to look for the work's file today: after each failed check, the wait doubles
    (1, 2, 4, 8, 16 days), up to MAX_DAYS_BETWEEN_CHECKS."""
    if not paper.failed_checks or not paper.last_check:
        return True
    try:
        last_check = dt.date.fromisoformat(paper.last_check)
    except ValueError:
        return True
    wait = min(2 ** (paper.failed_checks - 1), MAX_DAYS_BETWEEN_CHECKS)
    return today >= last_check + dt.timedelta(days=wait)


def add_new_works(papers: list[Paper], found: list[Paper]) -> list[Paper]:
    """Add to `papers` the found works it doesn't have, and return them.

    The works already in the list only get the new links: changing their title, year or authors
    would change their file name, and their downloaded file would no longer be found.
    """
    new = []
    for paper in found:
        twin = next((known for known in papers if same_work(known, paper)), None)
        if twin is None:
            new.append(paper)
        else:
            twin.pdf_urls.extend(url for url in paper.pdf_urls if url not in twin.pdf_urls)
    if new:
        # The new works may need a different file name; the old ones keep theirs.
        old_tags = [(paper, paper.filename_tag) for paper in papers]
        tag_repeated_filenames(papers + new)
        for paper, tag in old_tags:
            paper.filename_tag = tag
        papers.extend(new)
    return new


CALIBRE_STATES = {
    "uploaded": "Subida a Calibre (y borrada de la carpeta).",
    "kept": "Subida a Calibre, pero Calibre no muestra el archivo; se queda también en la carpeta.",
    "duplicate": "Calibre ya tenía una obra con ese título; no se ha subido y está en la carpeta.",
}


def on_download(paper: Paper, folder: Path) -> None:
    """Every downloaded work goes to Calibre, and the user gets a message."""
    if main.calibre:
        try:
            calibre_state = CALIBRE_STATES[main.send_to_calibre(paper, folder)]
        except Exception as error:
            calibre_state = f"No se ha podido subir a Calibre: {error}"
    else:
        calibre_state = "No hay Calibre configurado; está en la carpeta."
    # The log of the check says it too, not only Telegram.
    print(f"    {calibre_state} [{paper.source or 'enlace de OpenAlex'}]")
    lines = [
        "📥 Nueva obra descargada",
        f"{paper.title} ({paper.year or 's. f.'})",
        main.short_authors(paper),
        paper.journal or paper.publisher or paper.source or "",
        calibre_state,
        f"Carpeta: {folder.name}",
    ]
    send_message("\n".join(line for line in lines if line))


def main_check() -> None:
    lock = take_daily_lock()
    if lock is None:
        print("La revisión diaria ya está en marcha.")
        return
    try:
        lists = followed_lists()
        if not lists:
            print('No se sigue ningún autor (menú: "Autores que seguir").')
            return
        main.connect_calibre()
        main.DOWNLOAD_LISTENERS.append(on_download)
        source = OpenAlexSource()
        for papers_file in lists:
            try:
                check_author(source, papers_file)
            except Exception:
                # One author that fails doesn't stop the others.
                traceback.print_exc()
        print("\n✓ Revisión diaria terminada.")
    except Exception as error:
        traceback.print_exc()
        send_message(f"⚠️ La revisión diaria de paperScraper ha fallado: {error}")
        sys.exit(1)
    finally:
        main.quit_finder_drivers()
        lock.close()


if __name__ == "__main__":
    main_check()
