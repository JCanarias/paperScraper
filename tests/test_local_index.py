import pytest

import local_index
from local_index import LocalIndex


@pytest.fixture
def dialnet(tmp_path, monkeypatch):
    monkeypatch.setattr(local_index, "DATABASE_PATH", tmp_path / "indexes.sqlite")
    index = LocalIndex("Dialnet")
    index.save([
        {"id": "1", "title": "Crítica de la razón pura", "authors": ["Immanuel Kant"], "year": 1781},
        {"id": "2", "title": "Crítica de la razón práctica", "authors": ["Immanuel Kant"], "year": 1788},
        {"id": "3", "title": "Fenomenología del espíritu", "authors": ["Georg Wilhelm Friedrich Hegel"]},
    ])
    yield index
    index.database.close()


def titles(records):
    return sorted(record["title"] for record in records)


def test_a_title_is_found_by_all_its_words_without_accents(dialnet):
    assert titles(dialnet.search_by_title("critica razon pura", 10)) == ["Crítica de la razón pura"]
    assert len(dialnet.search_by_title("Crítica razón", 10)) == 2


def test_words_that_are_search_operators_are_searched_as_words(dialnet):
    assert dialnet.search_by_title("NOT AND", 10) == []


def test_a_replaced_record_is_found_by_its_new_title_only(dialnet):
    dialnet.save([{"id": "1", "title": "Prolegómenos", "authors": ["Immanuel Kant"]}])
    assert dialnet.search_by_title("razón pura", 10) == []
    assert titles(dialnet.search_by_title("prolegomenos", 10)) == ["Prolegómenos"]


def test_deleted_records_are_not_found(dialnet):
    dialnet.delete(["3"])
    assert dialnet.search_by_title("fenomenologia", 10) == []
    assert dialnet.count() == 2


def test_other_sources_are_not_searched(dialnet):
    philarchive = LocalIndex("PhilArchive")
    assert philarchive.search_by_title("critica", 10) == []
    philarchive.database.close()


def test_an_author_with_initials_finds_the_whole_name(dialnet):
    assert titles(dialnet.search_by_author("G. W. F. Hegel", 10)) == ["Fenomenología del espíritu"]
    assert dialnet.search_by_author("Karl Kant", 10) == []
