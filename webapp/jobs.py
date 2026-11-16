"""The long tasks of the web panel, each one a menu option run without questions.

The panel starts one at a time as its own process (`python -m webapp.jobs <task> [<json>]`), like the
menu runs main.py: its output goes to library/.web/job.log, which the panel shows while it runs.
"""
import datetime as dt
import json
import sys
from pathlib import Path

LIBRARY = Path("library")

# The tasks the panel offers: their name in the panel.
TASKS = {
    "retry": "Reintentar las obras pendientes",
    "upload": "Subir a Calibre lo ya descargado",
    "reviews": "Descargar las obras dudosas aceptadas",
    "indexes": "Actualizar los catálogos locales",
    "tag": "Poner metadatos a los archivos ya descargados",
    "daily": "Revisión diaria (ahora)",
}


def retry(_: dict) -> None:
    import main

    main.connect_calibre()
    main.retry_pending()


def upload(_: dict) -> None:
    import main

    main.connect_calibre()
    main.upload_downloaded()


def indexes(arguments: dict) -> None:
    from update_indexes import INDEXED_SOURCES, update_indexes

    names = [name for name in arguments.get("names") or [] if name in INDEXED_SOURCES]
    update_indexes(names or list(INDEXED_SOURCES))


def tag(_: dict) -> None:
    import main
    from sources.openalex import OpenAlexSource

    main.tag_downloaded_files(OpenAlexSource())


def reviews(arguments: dict) -> None:
    """Write the decisions taken in the panel and download the accepted works (as the menu does).

    `decisions` is {list path: {work key: true/false}}; the works without a decision stay pending.
    """
    import main
    from downloader import is_downloaded
    from reviews import apply_decisions, decide, needs_review
    from storage import load_papers, update_papers, work_key

    # The answers given in Telegram meanwhile go first, as in the menu.
    apply_decisions(LIBRARY)
    main.connect_calibre()
    for list_path, chosen in (arguments.get("decisions") or {}).items():
        papers_file = LIBRARY / list_path
        if not papers_file.is_file() or not papers_file.resolve().is_relative_to(LIBRARY.resolve()):
            continue
        folder = papers_file.parent
        papers = load_papers(papers_file)
        accepted = []
        for paper in papers:
            key = work_key(paper)
            if key in chosen and needs_review(paper, folder):
                decide(paper, bool(chosen[key]))
                if chosen[key]:
                    accepted.append(paper)
        update_papers(papers_file, papers)
        rejected = sum(not value for value in chosen.values())
        print(f"\n{folder.name}: {len(accepted)} aceptadas, {rejected} descartadas")
        if accepted:
            main.find_and_download_pdfs(accepted, folder)
            main.print_download_summary(accepted, folder)
            main.after_download(accepted, folder)
            for paper in papers:
                paper.downloaded = is_downloaded(paper, folder)
            update_papers(papers_file, papers)
    print("\n✓ Decisiones guardadas.")


def daily(_: dict) -> None:
    # As the "daily" container does at 6:00: with its log in library/.logs and today marked as done.
    from tower import scheduler

    scheduler.run_check(dt.date.today())


def run(task: str, arguments: dict) -> None:
    import main

    try:
        globals()[task](arguments)
    finally:
        main.quit_finder_drivers()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        sys.exit(f"Uso: python -m webapp.jobs {'|'.join(TASKS)} [json]")
    run(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
