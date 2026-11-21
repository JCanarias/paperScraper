"""The long tasks of the web panel, each one a menu option run without questions.

The panel starts one at a time as its own process (`python -m webapp.jobs <task> [<json> | @<json file>]`), like the
menu runs main.py: its output goes to library/.web/job.log, which the panel shows while it runs.
While it runs it holds library/.web/task.lock, and the daily check waits for it (tower/scheduler.py).
"""
import datetime as dt
import json
import sys
from dataclasses import asdict
from pathlib import Path

from storage import LIBRARY_FOLDER

WEB_FOLDER = LIBRARY_FOLDER / ".web"
# The last search by title: the panel shows it to choose what to download.
TITLE_RESULTS = WEB_FOLDER / "title_results.json"
# The bibliographies sent from the panel.
BIBLIOGRAPHY_FOLDER = WEB_FOLDER / "bibliographies"

# The tasks the panel offers: their name in the panel.
TASKS = {
    "author": "Buscar y descargar las obras de un autor",
    "title_search": "Buscar por palabras del título",
    "title_download": "Descargar las obras elegidas",
    "bibliography": "Descargar una bibliografía",
    "retry": "Reintentar las obras pendientes",
    "upload": "Subir a Calibre lo ya descargado",
    "reviews": "Descargar las obras dudosas aceptadas",
    "indexes": "Actualizar los catálogos locales",
    "tag": "Poner metadatos a los archivos ya descargados",
    "daily": "Revisión diaria (ahora)",
}


def label(task: str, arguments: dict) -> str:
    """The task's name in the panel, with what it is about."""
    if task == "author" and arguments.get("profiles"):
        return f"Autor: {max(arguments['profiles'], key=lambda profile: profile.get('works_count', 0))['name']}"
    if task in ("title_search", "title_download") and arguments.get("words"):
        verb = "Buscar" if task == "title_search" else "Descargar"
        return f"{verb}: «{arguments['words']}»"
    if task == "bibliography" and arguments.get("file"):
        return f"Bibliografía: {arguments['file']}"
    return TASKS[task]


def author(arguments: dict) -> None:
    import main
    from languages import using_languages
    from models import Author
    from sources.openalex import OpenAlexSource

    profiles = [Author(id=str(profile["id"]), name=str(profile["name"]), works_count=int(profile["works_count"]),
                       institutions=[str(name) for name in profile.get("institutions") or []])
                for profile in arguments.get("profiles") or []]
    if not profiles:
        sys.exit("No has elegido ningún autor.")
    language_choice = arguments.get("languages") or {"languages": [], "unknown_language": True}
    main.connect_calibre()
    # As in the menu: several OpenAlex profiles of one person make a single list, named after the biggest.
    main_author = max(profiles, key=lambda profile: profile.works_count)
    with using_languages(language_choice):
        main.download_author_works(OpenAlexSource(), profiles, main_author, main.author_folder(main_author),
                                   language_choice, ask_doubtful_works=False)


def title_search(arguments: dict) -> None:
    import main
    from sources.openalex import OpenAlexSource

    words = str(arguments.get("words") or "").strip()
    if not words:
        sys.exit("No has escrito ninguna palabra.")
    main.connect_calibre()
    found = main.find_by_title(OpenAlexSource(), words)
    WEB_FOLDER.mkdir(parents=True, exist_ok=True)
    TITLE_RESULTS.write_text(json.dumps({"words": words, "papers": [asdict(paper) for paper in found]},
                                        ensure_ascii=False), encoding="utf-8")
    if found:
        print(f"\n✓ {len(found)} obras: elige en el panel cuáles descargar.")


def title_download(arguments: dict) -> None:
    import main
    from models import Paper

    results = json.loads(TITLE_RESULTS.read_text(encoding="utf-8"))
    if results["words"] != arguments.get("words"):
        sys.exit("Los resultados han cambiado (otra búsqueda): vuelve a elegir.")
    papers = [Paper(**paper) for paper in results["papers"]]
    chosen = sorted({int(number) for number in arguments.get("chosen") or [] if 0 <= int(number) < len(papers)})
    if not chosen:
        sys.exit("No has elegido ninguna obra.")
    main.connect_calibre()
    words = results["words"]
    main.download_and_save_search(words, [papers[number] for number in chosen],
                                  main.search_folder(main.TITLE_SEARCH_FOLDER, words))


def bibliography(arguments: dict) -> None:
    import main
    from sources.openalex import OpenAlexSource

    file_path = (BIBLIOGRAPHY_FOLDER / str(arguments.get("file") or "")).resolve()
    if not file_path.is_file() or file_path.parent != BIBLIOGRAPHY_FOLDER.resolve():
        sys.exit("No encuentro el archivo de la bibliografía.")
    main.connect_calibre()
    main.download_bibliography(OpenAlexSource(), file_path)


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
    apply_decisions(LIBRARY_FOLDER)
    main.connect_calibre()
    for list_path, chosen in (arguments.get("decisions") or {}).items():
        papers_file = LIBRARY_FOLDER / list_path
        if not papers_file.is_file() or not papers_file.resolve().is_relative_to(LIBRARY_FOLDER.resolve()):
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
    from run_lock import take_panel_task_lock
    from sources.openalex import OpenAlexError

    lock = take_panel_task_lock()
    if lock is None:
        sys.exit("Ya hay otra tarea del panel en marcha.")
    try:
        globals()[task](arguments)
    except KeyboardInterrupt:
        # "Parar la tarea" in the panel: as Ctrl+C in the menu, what is done is kept.
        print("\n⏹ Tarea parada.")
        sys.exit(130)
    except OpenAlexError as error:
        # Usually the key's daily budget is spent: a clear message, not a traceback.
        print(f"\n{error}")
        sys.exit(1)
    finally:
        main.quit_finder_drivers()
        lock.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        sys.exit(f"Uso: python -m webapp.jobs {'|'.join(TASKS)} [json]")
    # "@<file>": the arguments are in that file (a long list of choices doesn't fit in the command line).
    if len(sys.argv) > 2 and sys.argv[2].startswith("@"):
        given = Path(sys.argv[2][1:]).read_text(encoding="utf-8")
    else:
        given = sys.argv[2] if len(sys.argv) > 2 else "{}"
    run(sys.argv[1], json.loads(given))
