import pytest

from pdf_finders.sci_hub import absolute_url, pdf_link_in_page


@pytest.mark.parametrize("page, link", [
    ('<meta name="citation_pdf_url" content="/storage/a.pdf">', "/storage/a.pdf"),
    ('<iframe src="/ads"></iframe><iframe src="//cdn.sci-hub.su/files/b.pdf">', "//cdn.sci-hub.su/files/b.pdf"),
    ('<a href="/c.pdf">', "/c.pdf"),
    ('<button onclick="location.href=\'/download/d\'">', "/download/d"),
    ("<p>article not found</p>", None),
])
def test_the_pdf_link_of_a_work_page(page, link):
    assert pdf_link_in_page(page) == link


@pytest.mark.parametrize("link, address", [
    ("/storage/a.pdf#view=FitH&amp;navpanes=0", "https://sci-hub.su/storage/a.pdf"),
    ("//zero.sci-hub.su/b.pdf", "https://zero.sci-hub.su/b.pdf"),
    ("https://moscow.sci-hub.su/c.pdf", "https://moscow.sci-hub.su/c.pdf"),
])
def test_relative_links_become_whole_addresses(link, address):
    assert absolute_url(link) == address
