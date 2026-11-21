"""The doubtful works: the ones found only in Internet Archive or Google Books are not downloaded
until the user says they are by the author.

Those two take the author from whoever uploaded or published the book, and it is often wrong
(a "History of Magic" by Einstein). A work also found in a reliable place (OpenAlex, a library
catalogue...) is not doubtful.

The user decides:
- in a search by author (a list to tick, main.py);
- with the buttons of a Telegram message, sent by the daily check (up to MAX_QUESTIONS_PER_DAY a day).
  The bot (telegram_bot/bot.py, outside Docker) runs `python reviews.py yes|no <id>` in the "daily"
  container, which writes the decision in library/.reviews/, and then `python reviews.py download`,
  which downloads the accepted works at once (unless the daily check is running: it does it at its end);
- in the menu, "Revisar obras dudosas".

A rejected work is never downloaded again, also after a new search of the author.
"""
import datetime as dt
import json
import secrets
import sys
from pathlib import Path

import calibre_sync
from downloader import is_downloaded
from models import Paper
from storage import LIBRARY_FOLDER, find_saved_lists, load_content, load_papers, update_papers

REVIEW_SOURCES = ("Internet Archive", "Google Books")
DECISIONS_FOLDER = LIBRARY_FOLDER / ".reviews"
# More questions a day would flood the chat; the rest are asked the following days.
MAX_QUESTIONS_PER_DAY = 20


def doubtful(paper: Paper) -> bool:
    """Found only in Internet Archive or Google Books."""
    places = {paper.source or "OpenAlex", *paper.also_found_in}
    return places <= set(REVIEW_SOURCES)


def needs_review(paper: Paper, folder: Path) -> bool:
    """A doubtful work the user hasn't decided on and that would be downloaded otherwise."""
    # In Calibre, or deleted there by the user (calibre_memory.py): nothing to ask.
    if paper.in_calibre:
        return False
    if paper.review == "pending":
        return True
    return paper.review is None and doubtful(paper) and not is_downloaded(paper, folder)


def set_pending(paper: Paper) -> None:
    """Don't download it until the user says so."""
    paper.review = "pending"
    paper.wanted = False


def decide(paper: Paper, accepted: bool) -> None:
    paper.review = "accepted" if accepted else "rejected"
    paper.wanted = accepted


def describe(paper: Paper, folder: Path | None = None) -> str:
    """The lines that let the user tell whether the work is the author's."""
    link = ""
    if paper.identifiers.get("internet_archive"):
        link = f"https://archive.org/details/{paper.identifiers['internet_archive']}"
    elif paper.pdf_urls:
        link = paper.pdf_urls[0]
    lines = [
        f"{paper.title} ({paper.year or 's. f.'})",
        ", ".join(paper.authors[:3]) + (" y otros" if len(paper.authors) > 3 else ""),
        " · ".join(part for part in (paper.source, paper.publisher or paper.journal, paper.language) if part),
        link,
        f"Carpeta: {folder.name}" if folder else "",
    ]
    return "\n".join(line for line in lines if line)


# --- Telegram -------------------------------------------------------------------------------

def ask_by_telegram(library: Path = LIBRARY_FOLDER, limit: int = MAX_QUESTIONS_PER_DAY) -> int:
    """Send a question with buttons for each pending work not asked yet; return how many were sent."""
    from telegram_notify import send_message

    asked = 0
    for papers_file in find_saved_lists(library):
        if asked >= limit:
            break
        papers = load_papers(papers_file)
        changed = False
        for paper in papers:
            if asked >= limit:
                break
            if paper.review != "pending" or paper.review_id or paper.in_calibre:
                continue
            review_id = secrets.token_hex(5)
            text = "🔎 ¿Es de este autor? ¿La descargo?\n" + describe(paper, papers_file.parent)
            if send_message(text, [("📥 Descargar", f"rv:yes:{review_id}"), ("🗑 Descartar", f"rv:no:{review_id}")]):
                paper.review_id = review_id
                changed = True
                asked += 1
        if changed:
            update_papers(papers_file, papers)
    return asked


def record_decision(review_id: str, accepted: bool, library: Path = LIBRARY_FOLDER) -> str:
    """Keep the decision taken in Telegram, to be applied under the daily lock; returns what to show."""
    found = find_by_review_id(review_id, library)
    if found is None:
        return "No encuentro esa obra (¿se ha borrado su lista?)."
    papers_file, paper = found
    if paper.review in ("accepted", "rejected"):
        return f"Ya estaba decidida: {'se descarga' if paper.review == 'accepted' else 'descartada'}."
    DECISIONS_FOLDER.mkdir(parents=True, exist_ok=True)
    from run_lock import daily_check_running

    (DECISIONS_FOLDER / f"{review_id}.json").write_text(json.dumps({"accepted": accepted}), encoding="utf-8")
    if not accepted:
        return "Descartada; no se volverá a descargar."
    if daily_check_running():
        return "Se descargará cuando termine la revisión diaria, que está en marcha."
    return "La busco ahora; te aviso cuando la tenga."


def find_by_review_id(review_id: str, library: Path = LIBRARY_FOLDER) -> tuple[Path, Paper] | None:
    for papers_file in find_saved_lists(library):
        for paper in load_papers(papers_file):
            if paper.review_id == review_id:
                return papers_file, paper
    return None


def apply_decisions(library: Path = LIBRARY_FOLDER) -> dict[Path, set[str]]:
    """Write the decisions taken in Telegram into the lists (call it with the daily lock taken).

    Returns the review ids of the accepted works, by list.
    """
    decisions = read_decisions()
    accepted: dict[Path, set[str]] = {}
    if not decisions:
        return accepted
    for papers_file in find_saved_lists(library):
        papers = load_papers(papers_file)
        decided = [paper for paper in papers if paper.review_id in decisions]
        for paper in decided:
            decide(paper, decisions[paper.review_id])
            if decisions[paper.review_id]:
                accepted.setdefault(papers_file, set()).add(paper.review_id)
        if decided:
            update_papers(papers_file, papers)
    for review_id in decisions:
        (DECISIONS_FOLDER / f"{review_id}.json").unlink(missing_ok=True)
    return accepted


def read_decisions() -> dict[str, bool]:
    """The decisions waiting in DECISIONS_FOLDER: whether each review id was accepted."""
    decisions = {}
    for decision_file in DECISIONS_FOLDER.glob("*.json") if DECISIONS_FOLDER.exists() else []:
        try:
            decisions[decision_file.stem] = json.loads(decision_file.read_text(encoding="utf-8"))["accepted"]
        except (OSError, ValueError, KeyError) as error:
            # Left there: it may still be being written, and is read next time.
            print(f"Aviso: no se ha podido leer la decisión {decision_file.name}: {error}")
    return decisions


def download_accepted(accepted: dict[Path, set[str]]) -> None:
    """Look for the files of the works just accepted in Telegram, and tell the user how it went.

    calibre_sync.connect() and the daily check's on_download must be set up by the caller.
    """
    import work_search

    for papers_file, review_ids in accepted.items():
        folder = papers_file.parent
        papers = load_papers(papers_file)
        calibre_sync.mark_papers(papers)
        # The daily check may have looked for some of them today already (their author is followed).
        today = dt.date.today().isoformat()
        chosen = [paper for paper in papers if paper.review_id in review_ids and not is_downloaded(paper, folder)
                  and not paper.in_calibre and not paper.sent_to_calibre and paper.last_check != today]
        if not chosen:
            continue
        print(f"\n{folder.name}: {len(chosen)} obras aceptadas en Telegram")
        try:
            work_search.find_and_download_pdfs(chosen, folder)
        finally:
            leave_for_the_daily_check(chosen, folder)
            for paper in papers:
                paper.downloaded = is_downloaded(paper, folder)
            update_papers(papers_file, papers)


def leave_for_the_daily_check(chosen: list[Paper], folder: Path) -> None:
    """The accepted works still without a file are retried from now on like any other pending work;
    the user is told."""
    from telegram_notify import send_message

    for paper in chosen:
        if not is_downloaded(paper, folder) and not paper.in_calibre:
            paper.failed_checks += 1
            paper.last_check = dt.date.today().isoformat()
            send_message(f"😕 No he encontrado archivo de «{paper.title}»; "
                         "se volverá a buscar en las próximas revisiones diarias.")


def download_now() -> None:
    """`python reviews.py download`: apply the Telegram decisions and download the accepted works,
    unless the daily check is running (it does the same at its end)."""
    import daily_check
    import work_search
    from run_lock import take_daily_lock

    lock = take_daily_lock()
    if lock is None:
        print("La revisión diaria está en marcha; lo hará ella al terminar.")
        return
    try:
        # Answers given while it downloads (several buttons in a row) find the lock taken:
        # this run takes them too.
        while accepted := apply_decisions():
            if daily_check.on_download not in work_search.DOWNLOAD_LISTENERS:
                calibre_sync.connect()
                work_search.DOWNLOAD_LISTENERS.append(daily_check.on_download)
            download_accepted(accepted)
    finally:
        work_search.quit_finder_drivers()
        lock.close()


# --- Menu -------------------------------------------------------------------------------------

def review_in_menu(library: Path = LIBRARY_FOLDER) -> None:
    """Menu "Revisar obras dudosas": tick the ones to download; the others are rejected."""
    from run_lock import daily_check_running

    if daily_check_running():
        print("La revisión diaria está en marcha; prueba cuando termine.")
        return
    apply_decisions(library)
    lists = lists_with_doubtful_works(library)
    if not lists:
        print("No hay obras dudosas por revisar.")
        return
    for papers_file, papers, waiting in lists:
        folder = papers_file.parent
        content = load_content(papers_file)
        print(f"\n{folder.name}: {len(waiting)} obras que solo están en Internet Archive o Google Books.")
        chosen = ask_doubtful(waiting, content.get("author", {}).get("name") or folder.name)
        if chosen is None:
            print("Se dejan para más tarde.")
            return
        for paper in waiting:
            decide(paper, any(paper is one for one in chosen))
        update_papers(papers_file, papers)
        if chosen:
            download_chosen(chosen, papers_file, papers)


def lists_with_doubtful_works(library: Path) -> list[tuple[Path, list[Paper], list[Paper]]]:
    """Each list with doubtful works to decide on: its file, its works and the doubtful ones."""
    lists = []
    for papers_file in find_saved_lists(library):
        papers = load_papers(papers_file)
        calibre_sync.mark_papers(papers)
        waiting = [paper for paper in papers if needs_review(paper, papers_file.parent)]
        if waiting:
            lists.append((papers_file, papers, waiting))
    return lists


def download_chosen(chosen: list[Paper], papers_file: Path, papers: list[Paper]) -> None:
    import work_search

    folder = papers_file.parent
    try:
        work_search.find_and_download_pdfs(chosen, folder)
    except KeyboardInterrupt:
        print("\n\n⏹ Búsqueda interrumpida por el usuario")
        work_search.quit_finder_drivers()
    work_search.print_download_summary(chosen, folder)
    work_search.after_download(chosen, folder)
    for paper in papers:
        paper.downloaded = is_downloaded(paper, folder)
    update_papers(papers_file, papers)


def ask_doubtful(waiting: list[Paper], author_name: str) -> list[Paper] | None:
    """Which of these doubtful works to download; None if the user presses Ctrl+C."""
    import questionary

    def label(paper: Paper) -> str:
        authors = ", ".join(paper.authors[:2])
        return f"{paper.title} ({paper.year or 's. f.'}) — {authors} [{paper.source}]"

    print("Internet Archive y Google Books ponen a veces el autor equivocado. "
          "Marca las que sí son suyas; las demás se descartan y no se vuelven a descargar.")
    return questionary.checkbox(
        f"¿Cuáles son de {author_name}?",
        choices=[questionary.Choice(label(paper), value=paper) for paper in waiting],
    ).ask()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("yes", "no"):
        print(record_decision(sys.argv[2], sys.argv[1] == "yes"))
    elif sys.argv[1:] == ["download"]:
        download_now()
    else:
        print("Uso: python reviews.py yes|no <id>  |  python reviews.py download")
        sys.exit(2)
