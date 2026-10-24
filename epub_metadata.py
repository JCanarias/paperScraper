"""Writes a book's details into its EPUB, in the places where Calibre looks for them.

An EPUB is a ZIP file. Its details are in the OPF file (the one META-INF/container.xml points to),
inside <metadata>, as Dublin Core fields: dc:title, dc:creator, dc:date, dc:publisher, dc:language
and dc:identifier. The series uses Calibre's own <meta name="calibre:series">.
Like in the PDFs, we leave out tags (dc:subject) and comments (dc:description).
"""
import os
import zipfile
from pathlib import Path

from lxml import etree

from models import Paper

OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
NAMESPACES = {"opf": OPF, "dc": DC, "c": CONTAINER}

# Fields we never want; Calibre shows them as tags and comments.
UNWANTED_FIELDS = ("subject", "description")


def write_epub_metadata(epub_path: Path, paper: Paper) -> None:
    with zipfile.ZipFile(epub_path) as epub:
        container = etree.fromstring(epub.read("META-INF/container.xml"))
        opf_path = container.xpath("//c:rootfile/@full-path", namespaces=NAMESPACES)[0]
        new_opf = rewrite_opf(epub.read(opf_path), paper)
        replace_file_in_zip(epub, epub_path, opf_path, new_opf)


def rewrite_opf(opf: bytes, paper: Paper) -> bytes:
    package = etree.fromstring(opf)
    metadata = package.find("opf:metadata", NAMESPACES)
    # The book's main identifier is used by the EPUB itself, so we never touch it.
    main_identifier = package.get("unique-identifier")

    remove_fields(metadata, UNWANTED_FIELDS)
    # Gutenberg puts the date of its digital edition ("1999" for Plato), which is misleading.
    if paper.source == "Gutenberg":
        remove_fields(metadata, ["date"])

    new_values = {
        "title": [paper.title],
        "creator": paper.authors,
        "date": [paper.best_date()],
        "publisher": [paper.publisher],
        "language": [paper.language],
    }
    for name, values in new_values.items():
        values = [value for value in values if value]
        # When we don't know a field, we keep what the EPUB already says.
        if values:
            remove_fields(metadata, [name])
            for value in values:
                add_field(metadata, name, value)

    identifiers = {"ISBN": paper.isbn, "DOI": paper.doi}
    for scheme, value in identifiers.items():
        if value:
            remove_identifier(metadata, scheme, main_identifier)
            # Calibre reads the scheme from opf:scheme, and also from the "urn:isbn:" style prefix.
            identifier = add_field(metadata, "identifier", f"urn:{scheme.lower()}:{value}")
            identifier.set(f"{{{OPF}}}scheme", scheme)

    if paper.journal:
        set_series(metadata, paper.journal, paper.volume)

    return etree.tostring(package, xml_declaration=True, encoding="utf-8")


def remove_fields(metadata: etree._Element, names: list[str]) -> None:
    for name in names:
        for element in metadata.findall(f"dc:{name}", NAMESPACES):
            remove_with_refinements(metadata, element)


def remove_identifier(metadata: etree._Element, scheme: str, main_identifier: str | None) -> None:
    for element in metadata.findall("dc:identifier", NAMESPACES):
        if element.get("id") == main_identifier:
            continue
        text = (element.text or "").lower()
        element_scheme = (element.get(f"{{{OPF}}}scheme") or "").lower()
        if element_scheme == scheme.lower() or text.startswith((f"{scheme.lower()}:", f"urn:{scheme.lower()}:")):
            remove_with_refinements(metadata, element)


def remove_with_refinements(metadata: etree._Element, element: etree._Element) -> None:
    # In EPUB 3, extra details of a field (its role, its sort name...) are separate
    # <meta refines="#id"> elements, which must go together with the field.
    element_id = element.get("id")
    if element_id:
        for meta in metadata.findall("opf:meta", NAMESPACES):
            if meta.get("refines") == f"#{element_id}":
                metadata.remove(meta)
    metadata.remove(element)


def add_field(metadata: etree._Element, name: str, value: str) -> etree._Element:
    element = etree.SubElement(metadata, f"{{{DC}}}{name}")
    element.text = value
    return element


def set_series(metadata: etree._Element, name: str, volume: str | None) -> None:
    for meta in metadata.findall("opf:meta", NAMESPACES):
        if meta.get("name") in ("calibre:series", "calibre:series_index"):
            metadata.remove(meta)
    etree.SubElement(metadata, f"{{{OPF}}}meta", name="calibre:series", content=name)
    if volume:
        etree.SubElement(metadata, f"{{{OPF}}}meta", name="calibre:series_index", content=volume)


def replace_file_in_zip(epub: zipfile.ZipFile, epub_path: Path, name: str, content: bytes) -> None:
    # A ZIP file can't be edited in place, so we copy everything to a new file and swap them.
    temporary_path = epub_path.with_suffix(".tmp")
    with zipfile.ZipFile(temporary_path, "w") as new_epub:
        for item in epub.infolist():
            data = content if item.filename == name else epub.read(item.filename)
            # The "mimetype" entry must stay first and uncompressed; the original order keeps it first.
            new_epub.writestr(item, data, compress_type=item.compress_type)
    epub.close()
    os.replace(temporary_path, epub_path)
