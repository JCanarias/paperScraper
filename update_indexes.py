"""Brings the local catalogues (Dialnet, PhilArchive, DOAB) up to date.

Run it by hand or from a scheduled task:
    .venv\\Scripts\\python.exe update_indexes.py [--max-minutes N] [dialnet] [philarchive] [doab]
The first Dialnet harvest is long (hours); it can be stopped at any moment (Ctrl+C or --max-minutes)
and the next run goes on where it stopped.
"""
import argparse

from sources.dialnet import DialnetSource
from sources.doab import DoabSource
from sources.philarchive import PhilArchiveSource

INDEXED_SOURCES = {"dialnet": DialnetSource, "philarchive": PhilArchiveSource, "doab": DoabSource}


def update_indexes(names: list[str], max_minutes: float | None = None) -> None:
    for name in names:
        source = INDEXED_SOURCES[name]()
        print(f"\nActualizando el índice de {source.name} ({source.index.count()} registros)...")
        try:
            complete = source.update_index(max_minutes)
        except KeyboardInterrupt:
            print(f"⏹ Interrumpido; la próxima vez se sigue donde se ha quedado.")
            raise
        except Exception as error:
            print(f"✗ No se ha podido actualizar {source.name}: {error}")
            continue
        state = "completo" if complete else "a medias (se seguirá la próxima vez)"
        print(f"✓ {source.name}: {source.index.count()} registros, {state}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Actualiza los catálogos locales.")
    parser.add_argument("sources", nargs="*", help=f"cuáles ({', '.join(INDEXED_SOURCES)}); por defecto, todas")
    parser.add_argument("--max-minutes", type=float, default=None, help="parar tras estos minutos por fuente")
    arguments = parser.parse_args()
    unknown = [name for name in arguments.sources if name not in INDEXED_SOURCES]
    if unknown:
        parser.error(f"fuentes desconocidas: {', '.join(unknown)}")
    try:
        update_indexes(arguments.sources or list(INDEXED_SOURCES), arguments.max_minutes)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
