"""A real Chrome for the websites that show a "checking your browser" page (Cloudflare and the like)
to every program: Cervantes, the BNE, Gallica, HathiTrust, the journals of the Universidad de Navarra;
and any other website whose answer is that check (downloader.py: TDX, RACO...). It also fills in
pages as a person would: the Munich library's download form (mdz.py).

A plain request gets that page instead of the answer. Copying the browser's cookies into `requests`
isn't enough (those websites also tell `requests` apart by how it connects), and they block fetch()
from inside the page too. So the browser opens each address as a person would: a page is read from
the screen, and a file is saved by the browser itself in a temporary folder.
"""
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

BROWSER_HOSTS = ("cervantesvirtual.com", "bne.es", "gallica.bnf.fr", "hathitrust.org", "revistas.unav.edu")
# The check pages, by their title or by the start of their text (some keep the website's title).
CHALLENGE_TEXTS = ("just a moment", "un momento", "verificación de seguridad", "verificación de acceso",
                   "se verifica su acceso", "attention required", "making sure you", "preparing to download",
                   "checking your browser", "verificando acceso")
PASS_TIMEOUT_SECONDS = 120
# Some checks (Cloudflare Turnstile) wait for a click on their box. The box takes a few seconds to
# be ready, and a click while it is still checking starts it again, so the clicks are well apart.
SECONDS_BETWEEN_CLICKS = 12
TURNSTILE_BOX = ".cf-turnstile, div[class*=turnstile]"
DOWNLOAD_TIMEOUT_SECONDS = 300
# A big file (a whole book) can take longer: the wait goes on while it keeps growing, up to this.
LONGEST_DOWNLOAD_SECONDS = 1800
PAGE_BUILD_SECONDS = 15
# A file starts downloading within this time after the page has passed the check; if not, it's a page.
DOWNLOAD_START_SECONDS = 8
# A calm pause between two requests to the same website, like a person reading. The BNE blocked
# the program when it asked for many PDFs in a row.
SECONDS_BETWEEN_REQUESTS = 5.0
# Cloudflare's page when the website refuses outright: waiting doesn't help.
BLOCKED_TEXTS = ("you have been blocked", "has sido bloqueado")


class BrowserError(Exception):
    pass


_driver = None
# The browser's temporary folder, and inside it the one of the current download.
_browser_folder: Path | None = None
_download_folder: Path | None = None
_last_request: dict[str, float] = {}
# Websites that refused the browser in this run, or whose check it didn't pass (BHL, CORE: two
# minutes each time): not asked again until the program restarts.
_blocked_hosts: set[str] = set()


def needs_browser(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith(BROWSER_HOSTS)


def get_page(url: str, wait_for: str | None = None) -> str:
    """The page's source (HTML, or the XML of an API answer), once its website's check is passed.

    Pages built by JavaScript can get `wait_for`, a text their source has once they are complete.
    """
    driver = _open(url)
    deadline = time.monotonic() + PAGE_BUILD_SECONDS
    while wait_for and wait_for not in driver.page_source and time.monotonic() < deadline:
        time.sleep(0.5)
    # Chrome shows an XML answer as a tree, and keeps the original XML in a hidden element.
    xml = driver.execute_script(
        "const source = document.getElementById('webkit-xml-viewer-source-xml');"
        "return source ? source.innerHTML : null;")
    return xml or driver.page_source


def open_page(url: str):
    """The browser, on the page at the address once past its check, to act on it as a person would (mdz.py)."""
    return _open(url)


def download(url: str) -> tuple[bytes | None, str]:
    """The file at the address, or None and the source of the page shown instead."""
    _new_download_folder(_get_driver())
    driver = _open(url)
    return _wait_for_file(driver, url)


def _new_download_folder(driver) -> None:
    """Each download gets its own folder. Some websites send their file twice (De Gruyter), and the
    second copy can arrive later: in the old folder, it can't be taken for the next work's file."""
    global _download_folder
    # Leave the last page first: while it is open it can still start a download.
    driver.get("about:blank")
    previous = _download_folder
    _download_folder = Path(tempfile.mkdtemp(dir=_browser_folder))
    driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
        "behavior": "allow", "downloadPath": str(_download_folder),
    })
    if previous and previous != _browser_folder:
        shutil.rmtree(previous, ignore_errors=True)


def _wait_for_file(driver, url: str) -> tuple[bytes | None, str]:
    started = last_growth = time.monotonic()
    size = 0
    while (time.monotonic() - last_growth < DOWNLOAD_TIMEOUT_SECONDS
           and time.monotonic() - started < LONGEST_DOWNLOAD_SECONDS):
        files = list(_download_folder.iterdir())
        current = _folder_size()
        if current != size:
            size, last_growth = current, time.monotonic()
        finished = [f for f in files if not f.name.endswith(".crdownload") and f.stat().st_size > 0]
        if finished and not any(f.name.endswith(".crdownload") for f in files):
            content = finished[0].read_bytes()
            finished[0].unlink()
            return content, ""
        if not files and time.monotonic() - started > DOWNLOAD_START_SECONDS:
            return None, driver.page_source
        time.sleep(0.5)
    raise BrowserError(f"la descarga de {url} no ha terminado a tiempo")


def _folder_size() -> int:
    size = 0
    for file in _download_folder.iterdir():
        try:
            size += file.stat().st_size
        except OSError:
            # Chrome renames the file when it ends.
            pass
    return size


def quit_browser() -> None:
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
    if _browser_folder:
        shutil.rmtree(_browser_folder, ignore_errors=True)


def _open(url: str):
    host = urlparse(url).hostname or ""
    if host in _blocked_hosts:
        raise BrowserError(f"{host} no deja entrar al navegador")
    wait = _last_request.get(host, 0) + SECONDS_BETWEEN_REQUESTS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    driver = _get_driver()
    driver.get(url)
    started = time.monotonic()
    last_click = started
    # When the check lets a file through, the browser saves it and keeps showing the check page.
    while _on_challenge(driver) and not any(_download_folder.iterdir()):
        if _shows(driver, BLOCKED_TEXTS):
            _blocked_hosts.add(host)
            raise BrowserError(f"{host} no deja entrar al navegador")
        if time.monotonic() - started > PASS_TIMEOUT_SECONDS:
            _blocked_hosts.add(host)
            raise BrowserError(f"{host} no deja pasar al navegador (comprobación de seguridad)")
        if time.monotonic() - last_click > SECONDS_BETWEEN_CLICKS:
            _click_turnstile(driver)
            last_click = time.monotonic()
        time.sleep(1)
    _last_request[host] = time.monotonic()
    return driver


def _on_challenge(driver) -> bool:
    return _shows(driver, CHALLENGE_TEXTS)


def _shows(driver, texts: tuple[str, ...]) -> bool:
    """Whether the page's title or the start of its text has one of these texts."""
    try:
        shown = driver.title + " " + driver.execute_script("return document.body ? document.body.innerText.slice(0, 400) : ''")
    except Exception:
        return False
    return any(text in shown.lower() for text in texts)


def _click_turnstile(driver) -> None:
    # The box is inside a closed shadow root that Selenium can't reach, so the click is sent
    # as a real mouse click at the box's place on the screen.
    box = driver.execute_script(
        "const box = document.querySelector(arguments[0]);"
        "if (!box) return null; const r = box.getBoundingClientRect();"
        "return r.width ? {x: r.left, y: r.top, height: r.height} : null;", TURNSTILE_BOX)
    if not box:
        return
    x, y = box["x"] + 30, box["y"] + box["height"] / 2
    for event in ("mousePressed", "mouseReleased"):
        driver.execute_cdp_cmd("Input.dispatchMouseEvent",
                               {"type": event, "x": x, "y": y, "button": "left", "clickCount": 1})


def _get_driver():
    global _driver, _browser_folder, _download_folder
    if _driver is None:
        from selenium import webdriver

        _browser_folder = _download_folder = Path(tempfile.mkdtemp(prefix="paperscraper-browser-"))
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("prefs", {
            "download.default_directory": str(_download_folder),
            "download.prompt_for_download": False,
            # Save PDFs instead of showing them.
            "plugins.always_open_pdf_externally": True,
        })
        # Inside a container (the tower) Chrome can't use its own sandbox.
        if os.environ.get("CHROME_IN_CONTAINER"):
            options.add_argument("--no-sandbox")
        _driver = webdriver.Chrome(options=options)
        _driver.set_page_load_timeout(DOWNLOAD_TIMEOUT_SECONDS)
        _driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        })
        _driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
            "behavior": "allow", "downloadPath": str(_download_folder),
        })
    return _driver
