from duplicates import merge_duplicates, same_work, title_words
from models import Paper


def make_paper(title, doi=None, authors=("Immanuel Kant",), year=1781, **details):
    return Paper(title=title, year=year, doi=doi, pdf_urls=[], authors=list(authors), **details)


def test_title_words_keep_numbers_and_drop_accents():
    assert title_words("Presentación 48-3") == ["presentacion", "48", "3"]


def test_the_same_doi_is_the_same_work():
    assert same_work(make_paper("A", doi="10.1/X"), make_paper("B", doi="10.1/x"))


def test_two_published_dois_are_two_works_even_with_the_same_title():
    assert not same_work(make_paper("Presentación", doi="10.1/a"), make_paper("Presentación", doi="10.1/b"))


def test_a_preprint_and_its_article_are_the_same_work():
    preprint = make_paper("Kritik der reinen Vernunft", doi="10.48550/arXiv.1", year=1780)
    article = make_paper("Kritik der reinen Vernunft", doi="10.1/k")
    assert same_work(preprint, article)


def test_a_translation_is_another_work():
    assert not same_work(make_paper("Kant", language="de"), make_paper("Kant", language="es"))


def test_a_long_title_republished_with_a_new_doi_is_the_same_work():
    first = make_paper("La solución de Kant al problema del amor", doi="10.1/old", year=1990)
    second = make_paper("La solución de Kant al problema del amor", doi="10.1/new", year=2018)
    assert same_work(first, second)


def test_merging_keeps_the_published_record_with_the_links_of_both():
    preprint = make_paper("Kritik der reinen Vernunft", doi="10.48550/arXiv.1")
    preprint.pdf_urls = ["https://arxiv.org/pdf/1"]
    article = make_paper("Kritik der reinen Vernunft", doi="10.1/k", journal="Kant-Studien")
    article.pdf_urls = ["https://journal.org/k.pdf"]

    merged = merge_duplicates([preprint, article])

    assert len(merged) == 1
    assert merged[0].doi == "10.1/k"
    assert merged[0].pdf_urls == ["https://journal.org/k.pdf", "https://arxiv.org/pdf/1"]
    assert merged[0].identifiers["preprint_doi"] == "10.48550/arXiv.1"
