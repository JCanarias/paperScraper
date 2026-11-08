"""Menu "Ver y borrar archivos de la biblioteca": look through library/ folder by folder and delete files.

Only files inside library/ are ever deleted, and only after the user confirms. When a deleted file is a
work of a saved list (papers.json), the list is updated so the work isn't downloaded again by
"Reintentar las obras pendientes" or the daily check (unless the user says otherwise).
"""
from pathlib import Path

import questionary

from downloader import downloaded_file
from models import Paper
from storage import PAPERS_FILENAME, load_papers, update_papers

CHECKBOX_INSTRUCTION = "\n  ↑/↓ moverse · Espacio marcar · Enter confirmar"


def human_size(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def folder_files(folder: Path) -> list[Path]:
    """The files of a folder (not in its subfolders), without papers.json and hidden files."""
    return sorted(path for path in folder.iterdir()
                  if path.is_file() and path.name != PAPERS_FILENAME and not path.name.startswith("."))


def folders_with_files(library: Path) -> list[Path]:
    # Hidden folders (.logs) are the program's, not downloads.
    folders = [library, *sorted(path for path in library.rglob("*") if path.is_dir()
                                and not any(part.startswith(".") for part in path.relative_to(library).parts))]
    return [folder for folder in folders if folder_files(folder)]


def inside(path: Path, library: Path) -> bool:
    return path.resolve().is_relative_to(library.resolve())


def papers_by_file(folder: Path) -> tuple[Path | None, list[Paper], dict[Path, Paper]]:
    """The folder's list (if it has one), its works, and the work each downloaded file belongs to."""
    papers_file = folder / PAPERS_FILENAME
    if not papers_file.exists():
        return None, [], {}
    papers = load_papers(papers_file)
    files = {}
    for paper in papers:
        file_path = downloaded_file(paper, folder)
        if file_path:
            files[file_path] = paper
    return papers_file, papers, files


def file_label(file_path: Path, paper: Paper | None) -> str:
    notes = [human_size(file_path.stat().st_size)]
    if paper and paper.in_calibre:
        notes.append("también en Calibre")
    if paper is None and file_path.suffix.lower() in (".pdf", ".epub"):
        notes.append("sin ficha")
    return f"{file_path.name}  ({', '.join(notes)})"


def browse_library(library: Path) -> None:
    if not library.exists():
        print(f"No existe la carpeta {library}.")
        return
    while True:
        folders = folders_with_files(library)
        if not folders:
            print(f"No hay ningún archivo en {library}.")
            return
        choices = []
        for folder in folders:
            files = folder_files(folder)
            size = sum(path.stat().st_size for path in files)
            name = "library" if folder == library else str(folder.relative_to(library))
            choices.append(questionary.Choice(f"{name}  ({len(files)} archivos, {human_size(size)})", value=folder))
        folder = questionary.select(
            "Elige una carpeta:",
            choices=[*choices, questionary.Separator(), questionary.Choice("Volver", value=None)],
        ).ask()
        if folder is None:
            return
        browse_folder(folder, library)


def browse_folder(folder: Path, library: Path) -> None:
    while True:
        files = folder_files(folder)
        if not files:
            print("La carpeta se ha quedado sin archivos.")
            return
        papers_file, papers, paper_of = papers_by_file(folder)
        print(f"\n{folder} ({len(files)} archivos)")
        for file_path in files:
            print(f"  {file_label(file_path, paper_of.get(file_path))}")
        choice = questionary.select(
            "¿Qué hacer?",
            choices=[
                questionary.Choice("Ver los datos de un archivo", value="details"),
                questionary.Choice("Borrar archivos", value="delete"),
                questionary.Choice("Volver a las carpetas", value="back"),
            ],
        ).ask()
        if choice in ("back", None):
            return
        if choice == "details":
            show_details(files, paper_of)
        else:
            delete_files(files, folder, library, papers_file, papers, paper_of)


def show_details(files: list[Path], paper_of: dict[Path, Paper]) -> None:
    file_path = questionary.select(
        "¿Qué archivo?",
        choices=[*(questionary.Choice(path.name, value=path) for path in files),
                 questionary.Choice("Volver", value=None)],
    ).ask()
    if file_path is None:
        return
    paper = paper_of.get(file_path)
    print(f"\n{file_path.name}\n  Tamaño: {human_size(file_path.stat().st_size)}")
    if paper is None:
        print("  No está en la lista de esta carpeta (papers.json).")
        return
    rows = [
        ("Título", paper.title), ("Autores", ", ".join(paper.authors or [])), ("Año", paper.year),
        ("Idioma", paper.language), ("Revista", paper.journal), ("DOI", paper.doi),
        ("En Calibre", "sí" if paper.in_calibre else "no"),
    ]
    for label, value in rows:
        if value:
            print(f"  {label}: {value}")
    print()


def delete_files(files: list[Path], folder: Path, library: Path, papers_file: Path | None,
                 papers: list[Paper], paper_of: dict[Path, Paper]) -> None:
    chosen = questionary.checkbox(
        "Marca los archivos que quieres borrar:",
        choices=[questionary.Choice(file_label(path, paper_of.get(path)), value=path) for path in files],
        instruction=CHECKBOX_INSTRUCTION,
    ).ask()
    if not chosen:
        return
    if not questionary.confirm(f"¿Borrar {len(chosen)} archivos? No se pueden recuperar.", default=False).ask():
        return
    in_list = [path for path in chosen if path in paper_of]
    # A work whose file is deleted is "pending" again; usually the user doesn't want it any more.
    forget = bool(in_list) and questionary.confirm(
        "¿Que no se vuelvan a descargar (ni al reintentar las pendientes ni en la revisión diaria)?",
        default=True,
    ).ask()

    deleted = 0
    for path in chosen:
        if not inside(path, library):
            print(f"  ✗ {path.name}: no está dentro de {library}; no se toca.")
            continue
        try:
            path.unlink()
            deleted += 1
        except OSError as error:
            print(f"  ✗ {path.name}: {error}")
            continue
        paper = paper_of.get(path)
        if paper:
            paper.downloaded = False
            if forget:
                paper.wanted = False
    if papers_file and in_list:
        update_papers(papers_file, papers)
    print(f"✓ Borrados {deleted} archivos.")
