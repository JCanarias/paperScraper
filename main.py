import re
from collections.abc import Callable
from pathlib import Path

import questionary

from downloader import add_metadata, download_paper, downloaded_file, is_downloaded
from models import Author, Paper
from pdf_finders.core import CoreFinder
from pdf_finders.custom_legal_source import CustomLegalSourceFinder
from pdf_finders.semantic_scholar import SemanticScholarFinder
from pdf_finders.selenium_fast import SeleniumSciHubFinder
from pdf_finders.unpaywall import UnpaywallFinder
from sources.base import BookSource
from sources.gutenberg import GutenbergSource
from sources.internet_archive import InternetArchiveSource
from sources.openalex import OpenAlexSource
from storage import find_saved_lists, load_papers, save_papers, save_search, update_papers

LIBRARY_FOLDER = Path("library")
TITLE_SEARCH_FOLDER = LIBRARY_FOLDER / "Búsquedas por título"
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
BOOK_SOURCES: list[BookSource] = [InternetArchiveSource(), GutenbergSource()]


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
    return f"{paper.year or '----'} · {title} — {short_authors(paper)}{pdf_mark}{source_mark}"


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
    choice = questionary.select(
        "¿Qué quieres hacer?",
        choices=[
            questionary.Choice(f"Descargar todos ({len(papers)})", value="all"),
            questionary.Choice("Elegir uno a uno", value="choose"),
            questionary.Choice("Cancelar", value="cancel"),
        ],
    ).ask()

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

        try:
            found_urls = finder.find_pdf_urls(pending)
        except Exception as error:
            print(f"Aviso: {type(finder).__name__} ha fallado: {error}")
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
        print(f"Buscando libros en {book_source.name}...", end=" ", flush=True)
        try:
            found = search(book_source)
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

    selected_papers = confirm_papers_to_download(papers + books)
    if not selected_papers:
        print("No se descarga nada.")
        return

    download_and_save_search(words, selected_papers, search_folder(TITLE_SEARCH_FOLDER, words))


def download_and_save_search(words: str, selected_papers: list[Paper], folder: Path) -> None:
    try:
        print(f"\nBuscando y descargando ({len(selected_papers)} obras)...")
        find_and_download_pdfs(selected_papers, folder)
    except KeyboardInterrupt:
        print("\n\n⏹ Búsqueda interrumpida por el usuario")
        quit_finder_drivers()
        return

    for paper in selected_papers:
        paper.downloaded = is_downloaded(paper, folder)
    print_download_summary(selected_papers, folder)

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

    for author in selected_authors:
        print(f"\n{'='*60}")
        print(f"Procesando: {author.name}")
        print(f"{'='*60}")

        papers = source.get_papers(author)
        books = find_books(
            lambda book_source: book_source.search_books_by_author(author.name, MAX_BOOKS_PER_SOURCE)
        )
        print(f"\nSe han encontrado {len(papers)} obras en OpenAlex y {len(books)} libros en otras bibliotecas.\n")
        papers += books
        if not papers:
            continue

        selected_papers = confirm_papers_to_download(papers)
        if not selected_papers:
            print("No se descarga nada.")
            continue

        folder = author_folder(author)
        try:
            print(f"\nBuscando y descargando ({len(selected_papers)} obras)...")
            find_and_download_pdfs(selected_papers, folder)
        except KeyboardInterrupt:
            print("\n\n⏹ Búsqueda interrumpida por el usuario")
            quit_finder_drivers()
            return

        print_download_summary(selected_papers, folder)
        # The list keeps every work found, so the files downloaded in earlier searches stay in it.
        for paper in papers:
            paper.downloaded = is_downloaded(paper, folder)

        papers_file = save_papers(author, papers, folder)
        print(f"✓ Lista guardada en {papers_file}\n")


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
        update_papers(papers_file, papers)

        for paper in papers:
            if is_downloaded(paper, folder):
                print(f"  {paper.title}")
                add_metadata(downloaded_file(paper, folder), paper)

    print("\n✓ Metadatos escritos.")


def main() -> None:
    source = OpenAlexSource()

    choice = questionary.select(
        "¿Cómo quieres buscar?",
        choices=[
            questionary.Choice("Por autor", value="author"),
            questionary.Choice("Por palabras del título", value="title"),
            questionary.Choice("Poner metadatos a los archivos ya descargados", value="tag"),
        ],
    ).ask()

    if choice == "author":
        search_by_author(source)
    elif choice == "title":
        search_by_title(source)
    elif choice == "tag":
        tag_downloaded_files(source)


if __name__ == "__main__":
    main()
