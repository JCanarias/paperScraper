"""Scanned pages joined in a PDF: the books made from page images (gallica_pages.py, djvu_pdf.py)."""
import io

import pikepdf
from PIL import Image


def images_to_pdf(pages: list[bytes], dpi: int = 160) -> bytes:
    """A PDF with one JPEG per page, kept as it is (no new compression), each page `dpi` pixels per inch."""
    pdf = pikepdf.new()
    for jpeg in pages:
        with Image.open(io.BytesIO(jpeg)) as image:
            width, height = image.size
            color_space = {"L": "/DeviceGray", "CMYK": "/DeviceCMYK"}.get(image.mode, "/DeviceRGB")
        picture = pikepdf.Stream(pdf, jpeg)
        picture.Type, picture.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        picture.Width, picture.Height, picture.BitsPerComponent = width, height, 8
        picture.ColorSpace = pikepdf.Name(color_space)
        picture.Filter = pikepdf.Name.DCTDecode
        # The page keeps the image's proportions (72 points per inch).
        page_width, page_height = width * 72 / dpi, height * 72 / dpi
        page = pikepdf.Dictionary(
            Type=pikepdf.Name.Page, MediaBox=[0, 0, page_width, page_height],
            Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=picture)),
            Contents=pikepdf.Stream(pdf, f"q {page_width:.2f} 0 0 {page_height:.2f} 0 0 cm /Im0 Do Q".encode()),
        )
        pdf.pages.append(pikepdf.Page(page))
    output = io.BytesIO()
    pdf.save(output)
    return output.getvalue()
