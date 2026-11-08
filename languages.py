"""The languages the works are searched and downloaded in (menu: "Idiomas").

Each source writes the language its own way ("es", "spa", "Spanish", "español"...), so they are turned
into the two-letter codes OpenAlex and Calibre use. The choice is kept in library/settings.json, which
the menu, the web terminal and the daily check share. With no language chosen, every one is allowed.

A search by author can choose its own languages; they are kept in the author's papers.json
("language_choice") and used for that author instead of the general ones (see `using_languages`).
"""
import json
from contextlib import contextmanager
from pathlib import Path

from models import Paper

SETTINGS_FILE = Path("library") / "settings.json"

# The languages offered in the menu, in this order.
LANGUAGE_NAMES = {
    "es": "Español", "en": "Inglés", "de": "Alemán", "fr": "Francés", "it": "Italiano",
    "pt": "Portugués", "la": "Latín", "el": "Griego", "ca": "Catalán", "gl": "Gallego",
    "eu": "Euskera", "nl": "Neerlandés", "pl": "Polaco", "ru": "Ruso",
}
# Three-letter codes (ISO 639-2, both forms) and names that the sources use.
OTHER_SPELLINGS = {
    "spa": "es", "eng": "en", "ger": "de", "deu": "de", "fre": "fr", "fra": "fr", "ita": "it",
    "por": "pt", "lat": "la", "gre": "el", "ell": "el", "grc": "el", "cat": "ca", "glg": "gl",
    "baq": "eu", "eus": "eu", "dut": "nl", "nld": "nl", "pol": "pl", "rus": "ru",
    "spanish": "es", "english": "en", "german": "de", "french": "fr", "italian": "it",
    "portuguese": "pt", "latin": "la", "greek": "el", "catalan": "ca", "galician": "gl",
    "basque": "eu", "dutch": "nl", "polish": "pl", "russian": "ru",
    "español": "es", "castellano": "es", "inglés": "en", "alemán": "de", "francés": "fr",
    "latín": "la", "griego": "el", "catalán": "ca", "gallego": "gl", "euskera": "eu",
}

# Sources whose language data is unreliable: their titles are checked too (paper_language_allowed).
TITLE_CHECKED_SOURCES = ("Internet Archive",)
# Short titles ("Manuel Kant") are often guessed wrong.
MIN_TITLE_WORDS_TO_GUESS = 4
MIN_GUESS_PROBABILITY = 0.95
# The offered languages that langdetect knows (not Latin, Galician or Basque).
GUESSABLE_LANGUAGES = {"es", "en", "de", "fr", "it", "pt", "el", "ca", "nl", "pl", "ru"}


def language_code(language: str | None) -> str | None:
    """The two-letter code of a language as a source writes it, or None if it is unknown."""
    if not language:
        return None
    # Some sources give several ("spa; lat"), or a region ("es-ES", "pt_BR"): the first one counts.
    text = language.strip().lower().replace("_", "-").split(";")[0].split(",")[0].strip()
    if text in OTHER_SPELLINGS:
        return OTHER_SPELLINGS[text]
    code = text.split("-")[0]
    if len(code) == 2 and code.isalpha():
        return code
    # A three-letter code not in the list ("vie", "hun") is a known language, just not one offered:
    # it must not pass as "unknown language".
    if len(code) == 3 and code.isalpha():
        return OTHER_SPELLINGS.get(code, code)
    return None


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


# The languages of the author being searched or checked, while `using_languages` is active.
_current_choice: dict | None = None


@contextmanager
def using_languages(choice: dict | None):
    """Use `choice` ({"languages": [...], "unknown_language": bool}) instead of the general languages.

    With None, the general ones (menu "Idiomas") are used.
    """
    global _current_choice
    previous = _current_choice
    _current_choice = choice
    try:
        yield
    finally:
        _current_choice = previous


def current_choice() -> dict:
    """The languages in use now: the author's, or the general ones."""
    choice = _current_choice if _current_choice is not None else load_settings()
    return {"languages": sorted(choice.get("languages") or []),
            "unknown_language": choice.get("unknown_language", True)}


def chosen_languages() -> set[str]:
    """The chosen languages; empty means all of them."""
    return set(current_choice()["languages"])


def unknown_language_allowed() -> bool:
    return current_choice()["unknown_language"]


def language_allowed(code: str | None) -> bool:
    chosen = chosen_languages()
    if not chosen:
        return True
    if code is None:
        return unknown_language_allowed()
    return code in chosen


def paper_language_allowed(paper: Paper) -> bool:
    if not language_allowed(language_code(paper.language)):
        return False
    # Internet Archive's language is what the uploader wrote, often wrong or missing: its titles are
    # checked too, and a title clearly in a language not chosen leaves the work out.
    if paper.source in TITLE_CHECKED_SOURCES and chosen_languages():
        title_language = clear_title_language(paper.title)
        if title_language and title_language not in chosen_languages():
            return False
    return True


def clear_title_language(title: str | None) -> str | None:
    """The language of a title, only when the guess is safe (long enough title, high probability)."""
    if not title or len(title.split()) < MIN_TITLE_WORDS_TO_GUESS:
        return None
    # The guesser doesn't know Latin, Galician or Basque, and takes them for other languages:
    # with one of them chosen, a guess could leave out a good work.
    if chosen_languages() - GUESSABLE_LANGUAGES:
        return None
    try:
        from langdetect import DetectorFactory, LangDetectException, detect_langs
    except ImportError:
        return None
    # Without a seed the guesser can answer differently each time.
    DetectorFactory.seed = 0
    try:
        best = detect_langs(title)[0]
    except LangDetectException:
        return None
    return best.lang.split("-")[0] if best.prob >= MIN_GUESS_PROBABILITY else None


def keep_chosen_languages(papers: list[Paper]) -> list[Paper]:
    """The works in the chosen languages; says how many were left out."""
    kept = [paper for paper in papers if paper_language_allowed(paper)]
    if len(kept) < len(papers):
        print(f"Se dejan fuera {len(papers) - len(kept)} obras en otros idiomas ({languages_label()}).")
    return kept


def languages_label() -> str:
    chosen = chosen_languages()
    if not chosen:
        return "todos los idiomas"
    order = list(LANGUAGE_NAMES)
    in_menu_order = sorted(chosen, key=lambda code: (order.index(code) if code in order else len(order), code))
    names = [LANGUAGE_NAMES.get(code, code) for code in in_menu_order]
    if unknown_language_allowed():
        names.append("sin idioma conocido")
    return ", ".join(names)
