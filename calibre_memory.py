"""Every work this program has sent to the user's Calibre library, so what they delete there is not
downloaded again.

The program only sees what Calibre has now: a book deleted in Calibre would look like a missing work
and be downloaded again (by the daily check, a new search, another author's list...). So every upload
adds the keys of the work here (identifiers like "doi:10.1/x", and "title words|surname"), and they are
never removed. A work that matches a key here but is no longer in Calibre was deleted by the user:
it counts as "in Calibre" and is never downloaded or uploaded again.

The books the user added to Calibre by hand are not kept here: if they delete one, it can be downloaded.

It is a SQLite file in the library folder (library/.calibre_memory.sqlite), shared by the menu, the
web terminal and the daily check.

To download again something deleted by mistake:  python calibre_memory.py forget "words of the title"
"""
import datetime as dt
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path

MEMORY_FILE = Path("library") / ".calibre_memory.sqlite"


class CalibreMemory:

    def __init__(self, path: Path = MEMORY_FILE):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.is_new = not path.exists()
        # The menu and the daily check can write at the same time; each waits for the other.
        self.database = sqlite3.connect(path, timeout=120)
        self.database.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, first_seen TEXT)")
        self.keys: set[str] = {row[0] for row in self.database.execute("SELECT key FROM seen")}

    def remember(self, keys: Iterable[str]) -> int:
        """Add these keys; return how many were new."""
        new = set(keys) - self.keys
        if new:
            today = dt.date.today().isoformat()
            with self.database:
                self.database.executemany("INSERT OR IGNORE INTO seen VALUES (?, ?)",
                                          [(key, today) for key in new])
            self.keys |= new
        return len(new)

    def knows(self, keys: Iterable[str]) -> bool:
        return any(key in self.keys for key in keys)

    def forget(self, words: str) -> list[str]:
        """Remove the keys whose title has these words; return them."""
        from duplicates import title_words

        wanted = " ".join(title_words(words))
        removed = sorted(key for key in self.keys if wanted and wanted in key.split("|")[0])
        with self.database:
            self.database.executemany("DELETE FROM seen WHERE key = ?", [(key,) for key in removed])
        self.keys -= set(removed)
        return removed

    def forget_id(self, key: str) -> bool:
        """Remove one identifier ("doi:10.1/x"); whether it was here."""
        key = key.strip().lower()
        with self.database:
            gone = self.database.execute("DELETE FROM seen WHERE key = ?", (key,)).rowcount
        self.keys.discard(key)
        return bool(gone)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "forget":
        removed = CalibreMemory().forget(sys.argv[2])
        for key in removed:
            print(f"  olvidado: {key}")
        print(f"{len(removed)} claves olvidadas; esas obras se pueden volver a descargar."
              if removed else "No hay ninguna obra con esas palabras en el título.")
        print("Si la obra tiene DOI o ISBN, olvídalos también: python calibre_memory.py forget-id doi:10.xxx")
    elif len(sys.argv) == 3 and sys.argv[1] == "forget-id":
        print("Olvidado." if CalibreMemory().forget_id(sys.argv[2]) else "No estaba.")
    else:
        print('Uso: python calibre_memory.py forget "palabras del título"  |  forget-id doi:10.xxx')
        sys.exit(2)
