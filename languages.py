"""The languages the works are searched and downloaded in (menu: "Idiomas").

Each source writes the language its own way ("es", "spa", "Spanish", "español"...), so they are turned
into the two-letter codes OpenAlex and Calibre use. The choice is kept in library/settings.json, which
the menu, the web terminal and the daily check share. With no language chosen, every one is allowed.
"""
import json
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


def language_code(language: str | None) -> str | None:
    """The two-letter code of a language as a source writes it, or None if it is unknown."""
    if not language:
        return None
    # Some sources give several ("spa; lat"), or a region ("es-ES", "pt_BR"): the first one counts.
    text = language.strip().lower().replace("_", "-").split(";")[0].split(",")[0].strip()
    if text in OTHER_SPELLINGS:
        return OTHER_SPELLINGS[text]
    code = text.split("-")[0]
    return code if len(code) == 2 and code.isalpha() else OTHER_SPELLINGS.get(code)


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def chosen_languages() -> set[str]:
    """The chosen languages; empty means all of them."""
    return set(load_settings().get("languages") or [])


def unknown_language_allowed() -> bool:
    return load_settings().get("unknown_language", True)


def language_allowed(code: str | None) -> bool:
    chosen = chosen_languages()
    if not chosen:
        return True
    if code is None:
        return unknown_language_allowed()
    return code in chosen


def paper_language_allowed(paper: Paper) -> bool:
    return language_allowed(language_code(paper.language))


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
