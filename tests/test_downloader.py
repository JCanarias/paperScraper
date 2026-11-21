import pytest

import browser_session
import downloader
from downloader import build_filename, file_extension, limited_content, pdf_link_in_html, tag_repeated_filenames
from models import Paper


def make_paper(title, authors=(), year=2000, doi=None):
    return Paper(title=title, year=year, doi=doi, pdf_urls=[], authors=list(authors))


def test_the_file_name_has_year_title_and_authors_without_forbidden_characters():
    paper = make_paper('What is "Enlightenment"?', ["Immanuel Kant", "Moses Mendelssohn"], 1784)
    assert build_filename(paper) == "1784 - What is Enlightenment - Immanuel Kant & Moses Mendelssohn.pdf"


def test_more_than_two_authors_are_shortened():
    paper = make_paper("Logic", ["A One", "B Two", "C Three"], None)
    assert build_filename(paper, "epub") == "Logic - A One et al.epub"


def test_works_that_would_share_a_file_name_get_their_doi_added():
    first = make_paper("Introduction", ["Immanuel Kant"], doi="10.1/a")
    second = make_paper("Introduction", ["Immanuel Kant"], doi="10.1/b")
    tag_repeated_filenames([second, first])
    assert first.filename_tag is None
    assert second.filename_tag == "10.1/b"
    assert build_filename(second).endswith("[10.1_b].pdf")


@pytest.mark.parametrize("content, extension", [
    (b"%PDF-1.7 ...", "pdf"), (b"PK\x03\x04mimetypeapplication/epub+zip", "epub"), (b"<html>", None),
])
def test_file_extension_by_its_first_bytes(content, extension):
    assert file_extension(content) == extension


def test_a_pdf_link_to_the_server_itself_is_moved_to_the_page_website():
    page = '<head><meta name="citation_pdf_url" content="http://localhost:4000/bitstreams/1/download"></head>'
    assert pdf_link_in_html(page, "https://roderic.uv.es/items/1") == "https://roderic.uv.es/bitstreams/1/download"


class FakeResponse:
    """What limited_content reads of a streamed requests.Response."""

    def __init__(self, chunks, length=None):
        self.chunks = chunks
        self.headers = {"content-length": str(length)} if length else {}
        self.url = "https://slow.example.org/book.pdf"
        self.closed = False

    def iter_content(self, chunk_size):
        yield from self.chunks

    def close(self):
        self.closed = True


def test_a_file_within_the_limit_is_read_whole():
    response = FakeResponse([b"%PDF", b"-1.7"])
    assert limited_content(response) == b"%PDF-1.7"
    assert response.closed


def test_a_file_larger_than_the_limit_is_stopped(monkeypatch):
    monkeypatch.setattr(downloader, "MAX_DOWNLOAD_BYTES", 5)
    with pytest.raises(browser_session.FileTooLarge):
        limited_content(FakeResponse([b"%PDF", b"-1.7"]))
    with pytest.raises(browser_session.FileTooLarge):
        limited_content(FakeResponse([], length=6))


def test_a_download_too_slow_marks_its_website_as_unresponsive(monkeypatch):
    monkeypatch.setattr(downloader, "LONGEST_DOWNLOAD_SECONDS", -1)
    monkeypatch.setattr(downloader, "UNRESPONSIVE_HOSTS", set())
    with pytest.raises(TimeoutError):
        limited_content(FakeResponse([b"%PDF"]))
    assert downloader.UNRESPONSIVE_HOSTS == {"slow.example.org"}
