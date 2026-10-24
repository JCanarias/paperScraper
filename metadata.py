"""Writes a paper's details into its PDF, in the places where Calibre looks for them.
(EPUB files are handled in epub_metadata.py.)

Calibre reads the XMP metadata block of the PDF (see calibre/ebooks/metadata/xmp.py):
- title, authors, publisher, date and language from the usual Dublin Core fields;
- identifiers (DOI, ISBN) from xmp:Identifier, and also from prism:doi / prism:isbn.
  We never use dc:identifier: Calibre saves whatever it finds there as a DOI, even an ISBN;
- the series from its own calibre:series field.
"""
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pikepdf
from pikepdf.models.metadata import encode_pdf_date

from epub_metadata import write_epub_metadata
from models import Paper

NAMESPACES = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "xmpidq": "http://ns.adobe.com/xmp/Identifier/qual/1.0/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
    "calibre": "http://calibre-ebook.com/xmp-namespace",
    "calibreSI": "http://calibre-ebook.com/xmp-namespace-series-index",
}
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

# Calibre puts the series index after the name, e.g. "Nature [521]". Without a volume, it uses 1.
DEFAULT_SERIES_INDEX = 1.0


def write_metadata(file_path: Path, paper: Paper) -> None:
    if file_path.suffix.lower() == ".epub":
        write_epub_metadata(file_path, paper)
    else:
        write_pdf_metadata(file_path, paper)


def write_pdf_metadata(pdf_path: Path, paper: Paper) -> None:
    # Calibre ignores the XMP block when the PDF's Info dictionary was modified later,
    # so both get exactly the same date.
    now = datetime.now().astimezone()

    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        pdf.Root.Metadata = pdf.make_stream(
            build_xmp_packet(paper, now),
            Type=pikepdf.Name.Metadata,
            Subtype=pikepdf.Name.XML,
        )
        fill_info_dictionary(pdf, paper, now)
        pdf.save(pdf_path)


def fill_info_dictionary(pdf: pikepdf.Pdf, paper: Paper, now: datetime) -> None:
    # The old metadata place; other PDF readers still use it.
    info = pdf.docinfo
    info[pikepdf.Name.Title] = paper.title
    # Calibre separates authors in this field with "&".
    info[pikepdf.Name.Author] = " & ".join(paper.authors)
    # Calibre turns these two into tags, and we don't want any; some PDFs come with them already.
    for name in (pikepdf.Name.Subject, pikepdf.Name.Keywords):
        if name in info:
            del info[name]
    info[pikepdf.Name.ModDate] = encode_pdf_date(now)


def build_xmp_packet(paper: Paper, now: datetime) -> bytes:
    root = ET.Element(tag("x:xmpmeta"))
    rdf = ET.SubElement(root, tag("rdf:RDF"))

    dc = new_description(rdf)
    add_language_alternative(dc, "dc:title", paper.title)
    add_list(dc, "dc:creator", paper.authors, ordered=True)
    if paper.publisher:
        add_list(dc, "dc:publisher", [paper.publisher])
    date = paper.best_date()
    if date:
        add_list(dc, "dc:date", [date], ordered=True)
    if paper.language:
        add_list(dc, "dc:language", [paper.language])

    identifiers = {"doi": paper.doi, "isbn": paper.isbn}
    identifiers = {scheme: value for scheme, value in identifiers.items() if value}

    xmp = new_description(rdf)
    ET.SubElement(xmp, tag("xmp:MetadataDate")).text = now.isoformat(timespec="seconds")
    if identifiers:
        add_identifiers(xmp, identifiers)
        # The same identifiers again, in the second place Calibre looks.
        prism = new_description(rdf)
        for scheme, value in identifiers.items():
            ET.SubElement(prism, tag(f"prism:{scheme}")).text = value

    if paper.journal:
        add_series(new_description(rdf), paper.journal, series_index(paper.volume))

    xml = ET.tostring(root, encoding="utf-8")
    return b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n' + xml + b'\n<?xpacket end="w"?>'


def series_index(volume: str | None) -> float:
    # The volume is usually a number ("521"), but sometimes it is something like "12-13".
    try:
        return float(volume)
    except (TypeError, ValueError):
        return DEFAULT_SERIES_INDEX


def tag(name: str) -> str:
    prefix, local_name = name.split(":")
    return f"{{{NAMESPACES[prefix]}}}{local_name}"


def new_description(rdf: ET.Element) -> ET.Element:
    return ET.SubElement(rdf, tag("rdf:Description"), {tag("rdf:about"): ""})


def add_language_alternative(parent: ET.Element, name: str, value: str) -> None:
    alternatives = ET.SubElement(ET.SubElement(parent, tag(name)), tag("rdf:Alt"))
    item = ET.SubElement(alternatives, tag("rdf:li"), {"{http://www.w3.org/XML/1998/namespace}lang": "x-default"})
    item.text = value


def add_list(parent: ET.Element, name: str, values: list[str], ordered: bool = False) -> None:
    # An ordered list (Seq) keeps the authors in their original order; a Bag has no order.
    values_list = ET.SubElement(ET.SubElement(parent, tag(name)), tag("rdf:Seq" if ordered else "rdf:Bag"))
    for value in values:
        ET.SubElement(values_list, tag("rdf:li")).text = value


def add_identifiers(parent: ET.Element, identifiers: dict[str, str]) -> None:
    bag = ET.SubElement(ET.SubElement(parent, tag("xmp:Identifier")), tag("rdf:Bag"))
    for scheme, value in identifiers.items():
        item = ET.SubElement(bag, tag("rdf:li"), {tag("rdf:parseType"): "Resource"})
        ET.SubElement(item, tag("xmpidq:Scheme")).text = scheme
        ET.SubElement(item, tag("rdf:value")).text = value


def add_series(parent: ET.Element, name: str, index: float) -> None:
    series = ET.SubElement(parent, tag("calibre:series"), {tag("rdf:parseType"): "Resource"})
    ET.SubElement(series, tag("rdf:value")).text = name
    ET.SubElement(series, tag("calibreSI:series_index")).text = f"{index:.2f}"
