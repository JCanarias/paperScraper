"""The user's Calibre library, seen from the downloads: which works it already has, and sending it the new files.

The connection is opened once per run (`connect`), when .env has CALIBRE_URL and the library answers;
`connected_library` is None otherwise, and then the files simply stay in the authors' folders.
A file is deleted from its folder only once Calibre confirms it has it.
"""
from pathlib import Path

import requests

import task_progress
from calibre_library import CalibreLibrary, identifier_keys, title_keys
from downloader import downloaded_file, is_downloaded
from models import MAX_TITLE_LENGTH_SHOWN, Paper
from storage import LIBRARY_FOLDER, find_saved_lists, load_papers, update_papers

connected_library: CalibreLibrary | None = None


def connect() -> None:
    global connected_library
    connected_library = CalibreLibrary.from_environment()
    if connected_library is None:
        return
    first_time = connected_library.memory is not None and connected_library.memory.is_new
    try:
        print(f"Calibre: {connected_library.load_index()} libros en la biblioteca.")
    except Exception as error:
        print(f"Aviso: no se puede leer la biblioteca de Calibre: {error}")
        connected_library = None
        return
    if first_time:
        remember_sent_works(connected_library)


def remember_sent_works(library: CalibreLibrary) -> None:
    """Start the memory of Calibre (calibre_memory.py) with the works sent before it existed:
    some may have been deleted in Calibre already, and then they would be downloaded again."""
    keys = set()
    for papers_file in find_saved_lists(LIBRARY_FOLDER):
        for paper in load_papers(papers_file):
            if paper.sent_to_calibre:
                keys |= identifier_keys(paper.all_identifiers()) | title_keys(paper.title, paper.authors)
    library.memory.remember(keys)


def mark_papers(papers: list[Paper]) -> int:
    """Set `in_calibre` on the works the library has or had; return how many. Without Calibre, none."""
    if connected_library is None:
        return 0
    return connected_library.mark_papers(papers)


def send_file(paper: Paper, folder: Path) -> str:
    """Upload the work's file; once Calibre confirms it has it, delete the local copy.

    Return "uploaded" (and deleted), "kept" (uploaded, but Calibre doesn't show the file, so it stays here)
    or "duplicate" (Calibre has a book with that title and didn't take it; the file stays here).
    """
    file_path = downloaded_file(paper, folder)
    book_id = connected_library.upload(file_path, paper)
    if book_id is None:
        return "duplicate"
    if not connected_library.book_has_format(book_id, file_path.suffix):
        return "kept"
    remove_local_copy(paper, file_path)
    return "uploaded"


def remove_local_copy(paper: Paper, file_path: Path) -> None:
    file_path.unlink()
    paper.sent_to_calibre = paper.in_calibre = True
    paper.downloaded = False


def remove_files_in_calibre(papers: list[Paper], folder: Path) -> int:
    """Delete the files of the works Calibre already has (same DOI, ISBN... and a file of that format)."""
    removed = 0
    for paper in papers:
        file_path = downloaded_file(paper, folder)
        if file_path and paper.in_calibre and connected_library.has_copy(paper, file_path.suffix):
            remove_local_copy(paper, file_path)
            removed += 1
    return removed


def upload_new_files(papers: list[Paper], folder: Path) -> None:
    """Send to Calibre the works of the list that have a file and that it doesn't have yet."""
    if connected_library is None:
        return
    new = [paper for paper in papers if not paper.in_calibre and is_downloaded(paper, folder)]
    if new:
        print(f"\nSubiendo a Calibre {len(new)} archivos nuevos...")
        upload_files(new, folder)


def upload_files(papers: list[Paper], folder: Path) -> None:
    uploaded = 0
    task_progress.step(f"Subiendo a Calibre {len(papers)} archivos")
    for paper in papers:
        print(f"  Subiendo {paper.title[:MAX_TITLE_LENGTH_SHOWN]}...", end=" ", flush=True)
        task_progress.trying(paper.title)
        try:
            result = send_file(paper, folder)
            if result == "uploaded":
                uploaded += 1
                print("✓")
                task_progress.uploaded(paper.title, True)
            elif result == "kept":
                uploaded += 1
                print("✓ (Calibre no muestra el archivo; se queda también aquí)")
                task_progress.uploaded(paper.title, True)
            else:
                print("ya estaba")
                task_progress.uploaded(paper.title, True, "ya estaba en Calibre")
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 403:
                print("\nEl usuario de Calibre no tiene permiso para añadir libros (es de solo lectura).")
                task_progress.uploaded(paper.title, False, "el usuario de Calibre es de solo lectura")
                return
            print(f"✗ ({error})")
            task_progress.uploaded(paper.title, False)
        except Exception as error:
            print(f"✗ ({error})")
            task_progress.uploaded(paper.title, False)
    print(f"✓ Subidos a Calibre: {uploaded}/{len(papers)}")


def upload_downloaded() -> None:
    """Send to Calibre every downloaded file it doesn't have, from all the lists."""
    if connected_library is None:
        print("No hay ninguna biblioteca de Calibre configurada (CALIBRE_URL en .env).")
        return
    anything_new = False
    for papers_file in find_saved_lists(LIBRARY_FOLDER):
        folder = papers_file.parent
        papers = load_papers(papers_file)
        connected_library.mark_papers(papers)
        # The files sent before (when they weren't deleted after uploading) go now.
        removed = remove_files_in_calibre(papers, folder)
        if removed:
            print(f"\n{folder}: borrados {removed} archivos que ya están en Calibre")
        new = [paper for paper in papers if not paper.in_calibre and is_downloaded(paper, folder)]
        if new:
            anything_new = True
            print(f"\n{folder}: {len(new)} archivos que no están en Calibre")
            upload_files(new, folder)
        if removed or new:
            update_papers(papers_file, papers)
    if not anything_new:
        print("✓ Todo lo descargado ya está en Calibre.")
