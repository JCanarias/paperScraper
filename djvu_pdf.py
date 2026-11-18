"""DjVu books (Wikimedia Commons has many) turned into PDF, which Calibre and every reader open.

DjVuLibre does it (ddjvu, installed in the tower's image). Most DjVu scans of printed books are black
and white: those become a black and white PDF at the scan's full resolution, compressed as a fax is
(CCITT G4: small and sharp; tiff2pdf). The ones with colour layers (pictures, coloured covers) become
one JPEG per page. Without DjVuLibre (on Windows) they can't be converted, so the sources leave DjVu
files out (available()).
"""
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from page_images import images_to_pdf

TOOLS = ("ddjvu", "djvudump", "djvused", "tiff2pdf")
# What djvudump shows for a layer in colour: the rest of a book's layers are black and white.
COLOR_LAYERS = ("(color)", "BGjp", "BG2k", "FGjp")
# Each colour page fits in a square of this size (the long side, about 160 ppp for an octavo).
COLOR_PAGE_SIZE = 1600
COLOR_PAGE_DPI = 160
JPEG_QUALITY = 75
CONVERSION_TIMEOUT_SECONDS = 1800


def available() -> bool:
    return all(shutil.which(tool) for tool in TOOLS)


def is_djvu(content: bytes) -> bool:
    return content.startswith(b"AT&TFORM")


def to_pdf(content: bytes) -> bytes:
    if not available():
        raise ValueError("falta DjVuLibre para convertir el DjVu a PDF")
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        book = folder / "book.djvu"
        book.write_bytes(content)
        if any(layer in run("djvudump", book) for layer in COLOR_LAYERS):
            return color_pdf(book, folder)
        run("ddjvu", "-format=tiff", "-mode=black", book, folder / "pages.tif")
        run("tiff2pdf", "-o", folder / "book.pdf", folder / "pages.tif")
        return (folder / "book.pdf").read_bytes()


def color_pdf(book: Path, folder: Path) -> bytes:
    pages = []
    page_count = int(run("djvused", "-e", "n", book).strip())
    for number in range(1, page_count + 1):
        image_path = folder / "page.ppm"
        run("ddjvu", "-format=ppm", f"-page={number}", f"-size={COLOR_PAGE_SIZE}x{COLOR_PAGE_SIZE}", book, image_path)
        with Image.open(image_path) as image:
            jpeg = io.BytesIO()
            image.convert("RGB").save(jpeg, "JPEG", quality=JPEG_QUALITY, optimize=True)
        pages.append(jpeg.getvalue())
    return images_to_pdf(pages, dpi=COLOR_PAGE_DPI)


def run(*arguments) -> str:
    finished = subprocess.run([str(argument) for argument in arguments], capture_output=True,
                              timeout=CONVERSION_TIMEOUT_SECONDS, check=True)
    return finished.stdout.decode("utf-8", errors="replace")
