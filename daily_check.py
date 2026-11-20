"""Daily check of the followed authors (menu: "Autores que seguir").

For each of them, as a new search by author would do, but without asking anything:
1. looks for works that weren't in its list yet (OpenAlex and the other libraries) and adds them;
   the ones not in Calibre are marked to download, except the doubtful ones (only in Internet Archive
   or Google Books), which wait for the user's answer in Telegram (reviews.py);
2. looks again for a file of every chosen work still without one (local catalogues and PDF finders);
   a work that keeps failing waits longer each time (1, 2, 4... up to 30 days), unless it gets new links;
3. sends every new file to Calibre and a Telegram message for each one.
At the end it asks about the doubtful works by Telegram, downloads the ones accepted meanwhile,
and sends a report by Telegram: what was found and downloaded, and the sources that failed.
The same report is kept for the web panel (daily_reports.py).

The tower runs it every day at 6:00 (the "daily" container, tower/scheduler.py). By hand:
    docker compose exec daily python daily_check.py
"""
import datetime as dt
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import daily_reports
import main
from downloader import is_downloaded, tag_repeated_filenames
from duplicates import merge_duplicates, same_work
from languages import keep_chosen_languages, languages_label, paper_language_allowed, using_languages
import sources.openalex
import task_progress
from models import Paper
from reviews import apply_decisions, ask_by_telegram, doubtful, download_accepted, needs_review, set_pending
from run_lock import take_daily_lock
from sources.openalex import OpenAlexSource
from storage import author_profiles, find_saved_lists, load_content, load_papers, set_content_value, update_papers
from telegram_notify import send_message

# The longest wait between two searches for the file of a work that keeps failing.
MAX_DAYS_BETWEEN_CHECKS = 30
# Asking OpenAlex for all the works of every author and searching every library takes about an hour each
# day (2026-11-16: an hour with only 6 works to look for). So each author gets that full search once a week,
# on a day of its own so they don't all fall on the same one; the other days, only the works published
# lately. (OpenAlex's filter by the day a work was added is only for paying members.)
FULL_SEARCH_EVERY_DAYS = 7
# Works published since this many days ago are looked for every day.
RECENT_WORKS_DAYS = 2 * 365
LAST_FULL_SEARCH_KEY = "last_full_search"
# What the daily check leaves of the OpenAlex key's daily budget (1 $ for a free key), for the menu.
OPENALEX_BUDGET_LEFT_FOR_MENU_USD = 0.30
# The lines of the check that tell about a problem (a source that fails, a catalogue not updated...).
PROBLEM_LINE = re.compile(r"Aviso|ha fallado|no responde|✗ No se ha podido")
MAX_PROBLEMS_IN_REPORT = 15


@dataclass
class AuthorResult:
    name: str
    new: int = 0
    downloaded: int = 0
    pending: int = 0
    failed: bool = False


@dataclass
class Report:
    """What the check did, for the message sent at its end."""
    started: float = field(default_factory=time.monotonic)
    started_at: dt.datetime = field(default_factory=dt.datetime.now)
    authors: dict[str, AuthorResult] = field(default_factory=dict)
    in_calibre: int = 0
    asked: int = 0
    # The works downloaded, for the panel: title, authors, year, folder, what happened in Calibre.
    downloads: list[dict] = field(default_factory=list)
    # Each problem line, and how many times it appeared.
    problems: dict[str, int] = field(default_factory=dict)

    def author(self, folder: Path) -> AuthorResult:
        # The folder is "Name (OpenAlex id)".
        name = re.sub(r"\s*\([^)]*\)$", "", folder.name) or folder.name
        return self.authors.setdefault(folder.name, AuthorResult(name))


report = Report()


class ProblemCollector:
    """Shows everything on the screen (and so in the log) as before, and keeps the problem lines."""

    def __init__(self, screen):
        self.screen = screen
        self.line = ""

    def write(self, text: str) -> int:
        self.screen.write(text)
        self.line += text
        *complete, self.line = self.line.split("\n")
        for line in complete:
            line = line.strip()
            if PROBLEM_LINE.search(line):
                # "Buscando libros en Gallica... ha fallado (...)" → "Gallica: ha fallado (...)"
                line = re.sub(r"^Buscando libros en (.+?)\.\.\.\s*", r"\1: ", line).removeprefix("Aviso: ")
                report.problems[line] = report.problems.get(line, 0) + 1
        return len(text)

    def __getattr__(self, name):
        return getattr(self.screen, name)


def followed_lists() -> list[Path]:
    return [papers_file for papers_file in find_saved_lists(main.LIBRARY_FOLDER)
            if load_content(papers_file).get("follow")]


def check_author(source: OpenAlexSource, papers_file: Path, position: int = 0) -> None:
    folder = papers_file.parent
    content = load_content(papers_file)
    papers = load_papers(papers_file)
    started = time.monotonic()
    print(f"\n{'=' * 60}\n{folder.name}  [{dt.datetime.now():%H:%M}]\n{'=' * 60}")
    task_progress.group(re.sub(r"\s*\([^)]*\)$", "", folder.name))
    # The languages chosen when this author was searched (or the general ones).
    try:
        with using_languages(content.get("language_choice")):
            print(f"Idiomas: {languages_label()}")
            check_author_works(source, papers_file, content, papers, position)
    finally:
        print(f"[{folder.name}: {(time.monotonic() - started) / 60:.1f} min]")


def full_search_today(content: dict, today: dt.date, position: int) -> bool:
    """Whether the author gets the full search today: on its own day of the week (from its place in the
    list of followed authors, so each day gets about as many), or when the last one is older than two
    weeks, or there was none."""
    try:
        last = dt.date.fromisoformat(content.get(LAST_FULL_SEARCH_KEY) or "")
    except ValueError:
        return True
    days = (today - last).days
    if days >= 2 * FULL_SEARCH_EVERY_DAYS:
        return True
    return days > 0 and today.toordinal() % FULL_SEARCH_EVERY_DAYS == position % FULL_SEARCH_EVERY_DAYS


def check_author_works(source: OpenAlexSource, papers_file: Path, content: dict, papers: list[Paper],
                       position: int = 0) -> None:
    folder = papers_file.parent
    today = dt.date.today()
    # A work that gets new links today (a new copy found) is tried today, whatever it failed before.
    links_before = {id(paper): len(paper.pdf_urls) for paper in papers}
    full = full_search_today(content, today, position)
    if full:
        print("Búsqueda completa (OpenAlex y bibliotecas)")
    else:
        print(f"Búsqueda rápida: obras de OpenAlex de los últimos {RECENT_WORKS_DAYS // 365} años "
              f"(la completa, una vez por semana)")
    try:
        since = None if full else today - dt.timedelta(days=RECENT_WORKS_DAYS)
        found = keep_chosen_languages(merge_duplicates(
            main.find_author_works(source, author_profiles(content), published_since=since)))
        if full:
            set_content_value(papers_file, LAST_FULL_SEARCH_KEY, today.isoformat())
    except Exception as error:
        # Without the new search, the pending works of the list are still looked for.
        print(f"Aviso: no se han podido buscar obras nuevas: {error}")
        found = []
    new = add_new_works(papers, found)
    if main.calibre:
        main.calibre.mark_papers(papers)
        if main.calibre.deleted_by_user:
            print(f"Borradas por ti en Calibre (no se descargan): {main.calibre.deleted_by_user}")
        removed = main.remove_files_in_calibre(papers, folder)
        if removed:
            print(f"Borrados {removed} archivos que ya están en Calibre")
    # As in a search by author: everything new that isn't in Calibre is downloaded, except the
    # doubtful works, which wait for the user (asked by Telegram at the end of the check).
    for paper in new:
        paper.wanted = not paper.in_calibre
        if paper.wanted and doubtful(paper):
            set_pending(paper)
    # The doubtful works chosen before the reviews existed are asked about too.
    for paper in papers:
        if paper.wanted and paper.review is None and needs_review(paper, folder):
            set_pending(paper)
    waiting = sum(paper.review == "pending" for paper in papers)
    print(f"Obras nuevas: {len(new)}" + (f"; dudosas por revisar: {waiting}" if waiting else ""))
    result = report.author(folder)
    result.new += len(new)

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
        result.pending = sum(paper.wanted and not paper.in_calibre and not paper.downloaded
                             and paper_language_allowed(paper) for paper in papers)


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
    report.author(folder).downloaded += 1
    if main.calibre:
        try:
            state = main.send_to_calibre(paper, folder)
            calibre_state = CALIBRE_STATES[state]
            report.in_calibre += state in ("uploaded", "kept")
        except Exception as error:
            calibre_state = f"No se ha podido subir a Calibre: {error}"
    else:
        calibre_state = "No hay Calibre configurado; está en la carpeta."
    # The log of the check says it too, not only Telegram.
    print(f"    {calibre_state} [{paper.source or 'enlace de OpenAlex'}]")
    report.downloads.append({
        "title": paper.title, "authors": paper.authors[:3], "year": paper.year,
        "source": paper.source or "enlace de OpenAlex", "author": report.author(folder).name, "calibre": calibre_state,
    })
    lines = [
        "📥 Nueva obra descargada",
        f"{paper.title} ({paper.year or 's. f.'})",
        main.short_authors(paper),
        paper.journal or paper.publisher or paper.source or "",
        calibre_state,
        f"Carpeta: {folder.name}",
    ]
    send_message("\n".join(line for line in lines if line))


def report_text() -> str:
    minutes = round((time.monotonic() - report.started) / 60)
    results = list(report.authors.values())
    downloaded = sum(result.downloaded for result in results)
    lines = [
        f"📋 Revisión diaria terminada ({minutes // 60} h {minutes % 60} min)",
        f"Autores revisados: {len(results)}",
        f"📥 Descargadas: {downloaded}" + (f" (subidas a Calibre: {report.in_calibre})" if main.calibre else ""),
        f"🆕 Obras nuevas: {sum(result.new for result in results)}",
        f"⏳ Siguen sin archivo: {sum(result.pending for result in results)}",
    ]
    if report.asked:
        lines.append(f"❓ Obras dudosas preguntadas: {report.asked}")
    # Only the authors with something to tell; the rest stay as they were.
    news = [result for result in results if result.new or result.downloaded or result.failed]
    if news:
        lines.append("")
        for result in news:
            if result.failed:
                lines.append(f"• {result.name}: ha fallado (mira el log)")
            else:
                lines.append(f"• {result.name}: {result.new} nuevas, {result.downloaded} descargadas, "
                             f"{result.pending} sin archivo")
    if report.problems:
        lines += ["", "⚠️ Problemas:"]
        for problem, times in list(report.problems.items())[:MAX_PROBLEMS_IN_REPORT]:
            lines.append(f"• {problem}" + (f" (×{times})" if times > 1 else ""))
        if len(report.problems) > MAX_PROBLEMS_IN_REPORT:
            lines.append(f"… y {len(report.problems) - MAX_PROBLEMS_IN_REPORT} más (mira el log)")
    else:
        lines += ["", "✅ Ninguna fuente ha dado problemas."]
    return "\n".join(lines)


def report_data(outcome: str, error: str = "") -> dict:
    """The report as the panel shows it; outcome is "ok", "failed" or "stopped"."""
    results = list(report.authors.values())
    return {
        "started": report.started_at.isoformat(timespec="minutes"),
        "ended": dt.datetime.now().isoformat(timespec="minutes"),
        "minutes": round((time.monotonic() - report.started) / 60),
        "outcome": outcome,
        "error": error,
        "authors_checked": len(results),
        "downloaded": sum(result.downloaded for result in results),
        "in_calibre": report.in_calibre if main.calibre else None,
        "new": sum(result.new for result in results),
        "pending": sum(result.pending for result in results),
        "asked": report.asked,
        "authors": [vars(result) for result in results if result.new or result.downloaded or result.failed],
        "downloads": report.downloads,
        "problems": [{"text": problem, "times": times} for problem, times in report.problems.items()],
    }


def main_check() -> None:
    sys.stdout = ProblemCollector(sys.stdout)
    lock = take_daily_lock()
    if lock is None:
        print("La revisión diaria ya está en marcha.")
        return
    try:
        lists = followed_lists()
        if not lists:
            print('No se sigue ningún autor (menú: "Autores que seguir").')
            return
        task_progress.groups(len(lists))
        main.connect_calibre()
        # The files left in the folders because Calibre didn't answer last time (2026-11-12 and 13) go first.
        if main.calibre:
            try:
                main.upload_downloaded()
            except Exception as error:
                print(f"Aviso: no se han podido subir a Calibre los archivos pendientes: {error}")
        main.DOWNLOAD_LISTENERS.append(on_download)
        sources.openalex.budget_to_keep_usd = OPENALEX_BUDGET_LEFT_FOR_MENU_USD
        # The answers given in Telegram since the last check.
        accepted = apply_decisions()
        source = OpenAlexSource()
        for position, papers_file in enumerate(lists):
            try:
                check_author(source, papers_file, position)
            except Exception:
                # One author that fails doesn't stop the others.
                traceback.print_exc()
                report.author(papers_file.parent).failed = True
        # The works accepted in Telegram (before or during the check) that are still without a file.
        for papers_file, review_ids in apply_decisions().items():
            accepted.setdefault(papers_file, set()).update(review_ids)
        download_accepted(accepted)
        asked = ask_by_telegram()
        if asked:
            print(f"\nPreguntadas por Telegram {asked} obras dudosas.")
        report.asked = asked or 0
        print("\n✓ Revisión diaria terminada.")
        send_message(report_text())
        daily_reports.save(report_data("ok"))
    except KeyboardInterrupt:
        # Stopped from the panel or by hand: what it did until then is kept.
        daily_reports.save(report_data("stopped"))
        raise
    except Exception as error:
        traceback.print_exc()
        send_message(f"⚠️ La revisión diaria de paperScraper ha fallado: {error}")
        daily_reports.save(report_data("failed", str(error)))
        sys.exit(1)
    finally:
        main.quit_finder_drivers()
        lock.close()


if __name__ == "__main__":
    main_check()
