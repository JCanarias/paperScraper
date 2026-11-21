import pytest

from languages import language_allowed, language_code, languages_label, using_languages


@pytest.mark.parametrize("written, code", [
    ("es", "es"), ("spa", "es"), ("Spanish", "es"), ("español", "es"), ("pt_BR", "pt"),
    ("spa; lat", "es"), ("vie", "vie"), ("", None), (None, None), ("12", None),
])
def test_language_code_understands_the_ways_sources_write_it(written, code):
    assert language_code(written) == code


def test_the_chosen_languages_are_allowed_and_the_rest_left_out():
    with using_languages({"languages": ["es", "de"], "unknown_language": False}):
        assert language_allowed("es")
        assert not language_allowed("en")
        assert not language_allowed(None)


def test_with_no_language_chosen_every_one_is_allowed():
    with using_languages({"languages": [], "unknown_language": False}):
        assert language_allowed("en")
        assert languages_label() == "todos los idiomas"


def test_the_label_follows_the_menu_order():
    with using_languages({"languages": ["de", "es"], "unknown_language": True}):
        assert languages_label() == "Español, Alemán, sin idioma conocido"
