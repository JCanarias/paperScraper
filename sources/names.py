import re
import unicodedata


def readable_name(name: str) -> str:
    """Turn a catalogue name ("Austen, Jane, 1775-1817") into a normal one ("Jane Austen")."""
    # Library catalogues add the author's dates after a comma; those parts have digits.
    parts = [part.strip() for part in name.split(",")]
    parts = [part for part in parts if part and not any(character.isdigit() for character in part)]
    if len(parts) == 2:
        last, first = parts
        return f"{first} {last}"
    return ", ".join(parts)


def name_words(name: str) -> list[str]:
    """Split a name into lowercase words without accents, so "José" and "jose" compare equal."""
    without_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", without_accents.lower())


def same_author(wanted: str, candidate: str) -> bool:
    """Whether `candidate` (a readable name from a library catalogue) can be the author `wanted`.

    OpenAlex often gives only initials ("W. K. C. Guthrie"), so the surname must be the same and
    both must have the same number of first names, and each one must agree with the other's word
    or initial in the same place: "W. K. C. Guthrie" matches "William Keith Chambers Guthrie",
    "William Guthrie" and "Donna W. Guthrie" don't.
    """
    wanted_words = name_words(wanted)
    candidate_words = name_words(candidate)
    if not wanted_words or wanted_words[-1] not in candidate_words:
        return False
    wanted_first_names = wanted_words[:-1]
    candidate_first_names = candidate_words[:candidate_words.index(wanted_words[-1])]
    if not wanted_first_names:
        return True
    # "William Guthrie" can be anyone with that name, so it doesn't match "William Keith Chambers Guthrie".
    if len(candidate_first_names) != len(wanted_first_names):
        return False
    return all(
        same_first_name(wanted_name, candidate_name)
        for wanted_name, candidate_name in zip(wanted_first_names, candidate_first_names)
    )


def same_first_name(one: str, other: str) -> bool:
    # An initial ("w") agrees with any name that starts with it ("william").
    if len(one) == 1 or len(other) == 1:
        return one[0] == other[0]
    return one == other
