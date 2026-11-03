"""Adds book files to the Calibre library of .env, through its content server.

    .venv\\Scripts\\python.exe add_books.py <files or folders...> [--duplicates] [--tag TAG]

Folders are read with their subfolders. Calibre takes the title, authors and the rest from the file;
every book also gets the tag CALIBRE_TAG ("paperScraper" by default). The books Calibre already has
(same title, ignoring capitals; Calibre does not look at the authors) are skipped unless --duplicates is given.
The files inside library/ are deleted once Calibre confirms it has them; the ones elsewhere are kept.
"""
import argparse
import os
import sys
from pathlib import Path

import requests

import config  # noqa: F401  (reads .env)
from calibre_library import CalibreLibrary

LIBRARY_FOLDER = Path(__file__).parent / "library"
BOOK_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw", ".azw3", ".djvu", ".fb2", ".docx", ".odt", ".rtf", ".txt",
                   ".cbz", ".cbr", ".lit", ".pdb"}


def find_books(paths: list[Path]) -> list[Path]:
    books = []
    for path in paths:
        if path.is_dir():
            books += sorted(file for file in path.rglob("*")
                            if file.is_file() and file.suffix.lower() in BOOK_EXTENSIONS)
        elif path.is_file():
            books.append(path)
        else:
            print(f"No existe: {path}")
    return books


def add_books(calibre: CalibreLibrary, books: list[Path], allow_duplicates: bool) -> None:
    added = repeated = failed = removed = 0
    for book in books:
        print(f"  {book.name}...", end=" ", flush=True)
        try:
            result = calibre.add_file(book, allow_duplicates)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 403:
                print("\nEl usuario de Calibre no tiene permiso para añadir libros (es de solo lectura).")
                return
            print(f"✗ ({error})")
            failed += 1
            continue
        except Exception as error:
            print(f"✗ ({error})")
            failed += 1
            continue
        if result.get("duplicates"):
            print("ya estaba")
            repeated += 1
        else:
            print(f"✓ {result.get('title', '')} — {' & '.join(result.get('authors', []))}")
            added += 1
            if remove_from_library(calibre, book, result["book_id"]):
                removed += 1
    print(f"\n✓ Añadidos: {added}   Ya estaban: {repeated}   Errores: {failed}   (tag: {calibre.tag})")
    if removed:
        print(f"  Borrados de library/: {removed}")


def remove_from_library(calibre: CalibreLibrary, book: Path, book_id: int) -> bool:
    """Delete the file if it is inside library/ and Calibre confirms it has it."""
    if not book.resolve().is_relative_to(LIBRARY_FOLDER.resolve()):
        return False
    try:
        if not calibre.book_has_format(book_id, book.suffix):
            print("    (Calibre no muestra el archivo; se queda en library/)")
            return False
    except Exception as error:
        print(f"    (no se ha podido comprobar en Calibre; se queda en library/: {error})")
        return False
    book.unlink()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Añade libros a la biblioteca de Calibre del .env.")
    parser.add_argument("paths", nargs="+", type=Path, help="archivos o carpetas")
    parser.add_argument("--duplicates", action="store_true", help="añadirlos aunque Calibre ya tenga uno igual")
    parser.add_argument("--tag", help="tag para estos libros (por defecto, CALIBRE_TAG o paperScraper)")
    arguments = parser.parse_args()

    if arguments.tag:
        os.environ["CALIBRE_TAG"] = arguments.tag
    calibre = CalibreLibrary.from_environment()
    if calibre is None:
        sys.exit("No hay ninguna biblioteca de Calibre a la que conectar (CALIBRE_URL en .env).")

    books = find_books(arguments.paths)
    if not books:
        sys.exit("No hay ningún libro que añadir.")
    print(f"Añadiendo {len(books)} libros a Calibre ({calibre.url})...")
    add_books(calibre, books, arguments.duplicates)


if __name__ == "__main__":
    main()
