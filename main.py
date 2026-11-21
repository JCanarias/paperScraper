"""The program's menu: what each option asks the user; the work itself is done in work_search.py."""
from collections.abc import Callable
from pathlib import Path

import questionary

import calibre_sync
from downloader import is_downloaded
from languages import LANGUAGE_NAMES, current_choice, languages_label, load_settings, save_settings, using_languages
from library_browser import browse_library
from manual_download import download_by_hand
from models import MAX_TITLE_LENGTH_SHOWN, Author, Paper, short_authors
from reviews import review_in_menu
from run_lock import daily_check_running
from sources.openalex import OpenAlexError, OpenAlexSource
from storage import (LIBRARY_FOLDER, PAPERS_FILENAME, find_saved_lists, load_content, load_papers, set_follow,
                     update_papers)
from update_indexes import INDEXED_SOURCES, update_indexes
from work_search import (TITLE_SEARCH_FOLDER, after_download, author_folder,
                         download_and_save_search, download_author_works, download_bibliography, find_by_title,
                         list_language_allowed, retry_pending, search_folder, tag_downloaded_files)

# How many works of each author are shown before choosing which author to download.
MAX_PREVIEW_PAPERS = 15


def author_label(author: Author) -> str:
    institutions = ", ".join(author.institutions) or "institución desconocida"
    return f"{author.name} ({author.works_count} obras) - {institutions}"


def choose_authors(source: OpenAlexSource, authors: list[Author]) -> list[Author]:
    if len(authors) == 1:
        return confirm_author(source, authors[0])

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


def confirm_author(source: OpenAlexSource, author: Author) -> list[Author]:
    """The only author found, once the user confirms it is the one they meant."""
    print(f"\nSolo un autor coincide con ese nombre:\n  {author_label(author)}")
    while True:
        choice = questionary.select(
            "¿Es este autor?",
            choices=[
                questionary.Choice("Sí, descargar sus obras", value="yes"),
                questionary.Choice("Ver sus obras más citadas", value="preview"),
                questionary.Choice("No, cancelar", value="cancel"),
            ],
        ).ask()
        # ask() returns None when the user presses Ctrl+C.
        if choice is None or choice == "cancel":
            return []
        if choice == "yes":
            return [author]
        preview_author(source, author)


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


def search_by_title(source: OpenAlexSource) -> None:
    words = input("Palabras del título: ").strip()
    if not words:
        print("No has escrito ninguna palabra.")
        return

    found = find_by_title(source, words)
    if not found:
        return
    selected_papers = confirm_papers_to_download(found)
    if not selected_papers:
        print("No se descarga nada.")
        return

    download_and_save_search(words, selected_papers, search_folder(TITLE_SEARCH_FOLDER, words))


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
    folder = author_folder(main_author)
    language_choice = ask_author_languages(folder)
    if language_choice is None:
        print("No se descarga nada.")
        return
    with using_languages(language_choice):
        download_author_works(source, selected_authors, main_author, folder, language_choice)


def ask_author_languages(folder: Path) -> dict | None:
    """The languages to search this author's works in, starting from the ones of their last search
    (or the general ones); None if the user presses Ctrl+C."""
    papers_file = folder / PAPERS_FILENAME
    earlier = load_content(papers_file).get("language_choice") if papers_file.exists() else None
    with using_languages(earlier):
        print(f"\nIdiomas{' de la última búsqueda de este autor' if earlier else ''}: {languages_label()}.")
        return ask_languages("Idiomas de sus obras que buscar y descargar (sin ninguno marcado: todos):")


def download_pending_by_hand() -> None:
    """Open in the browser, one by one, the chosen works that still have no file."""
    for papers_file in find_saved_lists(LIBRARY_FOLDER):
        folder = papers_file.parent
        papers = load_papers(papers_file)
        calibre_sync.mark_papers(papers)
        pending = [paper for paper in papers
                   if paper.wanted and not paper.in_calibre and not is_downloaded(paper, folder)
                   and list_language_allowed(papers_file, paper)]
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


def search_by_bibliography(source: OpenAlexSource) -> None:
    path_text = questionary.path("Archivo de la bibliografía (.bib, .ris o .txt con una referencia por línea):").ask()
    if not path_text:
        return
    file_path = Path(path_text.strip().strip('"'))
    if not file_path.is_file():
        print(f"No existe el archivo {file_path}.")
        return
    download_bibliography(source, file_path)


def choose_languages() -> None:
    """Choose the general languages the works are searched and downloaded in."""
    print(f"Ahora: {languages_label()}.")
    print("(Un autor buscado con otros idiomas sigue con los suyos, también en la revisión diaria.)")
    choice = ask_languages("Marca los idiomas en los que buscar y descargar (sin ninguno marcado: todos):")
    # Ctrl+C: nothing changes.
    if choice is None:
        return
    settings = load_settings()
    settings.update(choice)
    save_settings(settings)
    print(f"✓ Idiomas: {languages_label()}.")


def ask_languages(question: str) -> dict | None:
    """Ask for languages, starting from the ones in use; None if the user presses Ctrl+C."""
    current = current_choice()
    chosen = set(current["languages"])
    answer = questionary.checkbox(
        question,
        choices=[
            *(questionary.Choice(f"{name} ({code})", value=code, checked=code in chosen)
              for code, name in LANGUAGE_NAMES.items()),
            questionary.Separator(),
            questionary.Choice("Obras sin idioma conocido", value="unknown",
                               checked=bool(chosen) and current["unknown_language"]),
        ],
        instruction="\n  ↑/↓ moverse · Espacio marcar · Enter confirmar",
    ).ask()
    if answer is None:
        return None
    # Codes chosen before that the menu doesn't offer (edited by hand) are kept.
    languages = sorted({code for code in answer if code != "unknown"} | (chosen - set(LANGUAGE_NAMES)))
    return {"languages": languages, "unknown_language": "unknown" in answer or not languages}


def choose_followed_authors() -> None:
    """Choose the authors whose new works and files the daily check looks for."""
    lists = [(papers_file, load_content(papers_file)) for papers_file in find_saved_lists(LIBRARY_FOLDER)]
    author_lists = [(papers_file, content) for papers_file, content in lists if "author" in content]
    if not author_lists:
        print("Todavía no se ha buscado ningún autor.")
        return
    followed = questionary.checkbox(
        "Marca los autores que se revisan cada día:",
        choices=[
            questionary.Choice(papers_file.parent.name, value=papers_file, checked=content.get("follow", False))
            for papers_file, content in author_lists
        ],
        instruction="\n  ↑/↓ moverse · Espacio marcar · Enter confirmar",
    ).ask()
    # ask() returns None when the user presses Ctrl+C: nothing changes.
    if followed is None:
        return
    for papers_file, content in author_lists:
        if content.get("follow", False) != (papers_file in followed):
            set_follow(papers_file, papers_file in followed)
    print(f"✓ Se revisan cada día {len(followed)} autores.")


def main() -> None:
    source = OpenAlexSource()
    if daily_check_running():
        print("Aviso: la revisión diaria está en marcha; lo que hagas ahora puede chocar con ella.")
    calibre_sync.connect()

    options = menu_options(source)
    chosen_action = questionary.select(
        "¿Cómo quieres buscar?",
        choices=[questionary.Choice(label, value=action) for label, action in options],
    ).ask()
    # ask() returns None when the user presses Ctrl+C.
    if chosen_action is None:
        return
    try:
        chosen_action()
    except OpenAlexError as error:
        # Usually the key's daily budget is spent: a clear message, not a traceback.
        print(f"\n{error}")


def menu_options(source: OpenAlexSource) -> list[tuple[str, Callable[[], None]]]:
    """Each option of the menu, in its order, with what it runs."""
    return [
        ("Por autor", lambda: search_by_author(source)),
        ("Por palabras del título", lambda: search_by_title(source)),
        ("Desde una bibliografía (BibTeX, RIS o texto)", lambda: search_by_bibliography(source)),
        ("Reintentar las obras pendientes", retry_pending),
        ("Descargar a mano las pendientes (en el navegador)", download_pending_by_hand),
        ("Subir a Calibre lo ya descargado", calibre_sync.upload_downloaded),
        ("Ver y borrar archivos de la biblioteca", lambda: browse_library(LIBRARY_FOLDER)),
        ("Revisar obras dudosas (Internet Archive, Google Books)", lambda: review_in_menu(LIBRARY_FOLDER)),
        ("Actualizar los catálogos locales (Dialnet, PhilArchive, DOAB)",
         lambda: update_indexes(list(INDEXED_SOURCES))),
        ("Poner metadatos a los archivos ya descargados", lambda: tag_downloaded_files(source)),
        ("Autores que seguir (revisión diaria)", choose_followed_authors),
        (f"Idiomas ({languages_label()})", choose_languages),
    ]


if __name__ == "__main__":
    main()
