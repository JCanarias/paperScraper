"""Copies a library's catalogue through OAI-PMH, the protocol libraries offer for exactly that.

The catalogue comes in pages; each page ends with a "resumption token" for the next one.
We save the token after every page, so an interrupted harvest goes on where it stopped,
and remember the date of the last complete harvest, so the next one only asks for what changed.
"""
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone

import requests

from local_index import LocalIndex

TIMEOUT_SECONDS = 120
# Libraries ask harvesters to go slowly; Dialnet blocks for a while after bursts of requests.
SECONDS_BETWEEN_PAGES = 3
SECONDS_AFTER_REFUSAL = 120
MAX_REFUSALS = 6
HEADERS = {"User-Agent": "paperScraper/1.0 (https://github.com/JCanarias/paperScraper)"}
NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def harvest(index: LocalIndex, base_url: str, parse: Callable[[ET.Element], dict | None],
            set_name: str | None = None, max_minutes: float | None = None) -> bool:
    """Bring the index up to date; return True when the harvest is complete.

    `parse` turns a record's <oai_dc:dc> element into a dict for LocalIndex.save (without "id",
    which comes from the record's header), or None to skip it.
    With `max_minutes`, it stops after that time and goes on in the next call.
    """
    started = time.time()
    token = index.get_state("resumption_token")
    # The date is taken now, so whatever changes during the harvest is asked for again next time.
    harvest_date = index.get_state("harvest_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    index.set_state("harvest_date", harvest_date)
    pages = 0

    while True:
        if token:
            params = {"verb": "ListRecords", "resumptionToken": token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
            if set_name:
                params["set"] = set_name
            last_complete = index.get_state("last_complete")
            if last_complete:
                params["from"] = last_complete

        root = request_page(base_url, params)
        error = root.find("oai:error", NAMESPACES)
        if error is not None:
            if error.get("code") == "noRecordsMatch":
                break
            if error.get("code") == "badResumptionToken":
                # Tokens expire (Dialnet's after an hour); start again from the last complete harvest.
                print("  (el enlace a la página siguiente ha caducado; se sigue desde el principio)")
                token = None
                index.set_state("resumption_token", None)
                continue
            raise RuntimeError(f"{error.get('code')}: {error.text}")

        save_page(index, root, parse)
        pages += 1
        token_element = root.find(".//oai:resumptionToken", NAMESPACES)
        token = (token_element.text or "").strip() if token_element is not None else ""
        index.set_state("resumption_token", token or None)
        if pages % 10 == 0:
            print(f"  {pages} páginas, {index.count()} registros en el índice")
        if not token:
            break
        if max_minutes is not None and time.time() - started > max_minutes * 60:
            return False
        time.sleep(SECONDS_BETWEEN_PAGES)

    index.set_state("last_complete", harvest_date)
    index.set_state("harvest_date", None)
    return True


def request_page(base_url: str, params: dict) -> ET.Element:
    for refusal in range(1, MAX_REFUSALS + 1):
        try:
            response = requests.get(base_url, params=params, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            # 503 (and 429) mean "too many requests, come back later".
            if response.status_code not in (429, 503):
                response.raise_for_status()
                return ET.fromstring(response.content)
        except requests.ConnectionError:
            pass
        wait = SECONDS_AFTER_REFUSAL * refusal
        print(f"  El servidor pide esperar; se reintenta en {wait // 60} min...")
        time.sleep(wait)
    raise RuntimeError("el servidor sigue rechazando las peticiones; inténtalo más tarde")


def save_page(index: LocalIndex, root: ET.Element, parse: Callable[[ET.Element], dict | None]) -> None:
    records, deleted = [], []
    for record in root.iterfind(".//oai:record", NAMESPACES):
        header = record.find("oai:header", NAMESPACES)
        identifier = header.findtext("oai:identifier", "", NAMESPACES)
        if header.get("status") == "deleted":
            deleted.append(identifier)
            continue
        dc = record.find(".//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
        if dc is None:
            continue
        try:
            parsed = parse(dc)
        except Exception:
            # One strange record shouldn't stop the harvest.
            parsed = None
        if parsed:
            # The header's id, so a later deletion of the record removes it from the index too.
            parsed["id"] = identifier_to_id(identifier)
            records.append(parsed)
    index.save(records)
    if deleted:
        index.delete([identifier_to_id(identifier) for identifier in deleted])


def identifier_to_id(identifier: str) -> str:
    # "oai:dialnet.unirioja.es:ART0000157610" / "oai:philarchive.org/rec/ABCD": the last part.
    return identifier.replace("/", ":").rsplit(":", 1)[-1]


def dc_values(dc: ET.Element, name: str) -> list[str]:
    return [element.text.strip() for element in dc.iterfind(f"dc:{name}", NAMESPACES) if element.text]


def readable_name(name: str) -> str:
    # "Vigo, Alejandro G." -> "Alejandro G. Vigo"
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return name.strip()


def year_from(text: str | None) -> int | None:
    digits = "".join(character for character in (text or "")[:4] if character.isdigit())
    return int(digits) if len(digits) == 4 else None
