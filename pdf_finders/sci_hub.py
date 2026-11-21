"""Sci-Hub, through a real browser: its pages first show a CAPTCHA (an "Are you a robot?" question), which
the browser answers by clicking "No"; after that, each work's page gives the address of its PDF.

The class keeps its old name: the days of its last search are saved in each list under it (finder_misses).
"""
import html
import re
import time
from urllib.parse import quote, urldefrag, urljoin

from pdf_finders.base import DoiPdfFinder

SCI_HUB_URL = "https://sci-hub.su/"
CAPTCHA_TAG = "altcha-widget"
CAPTCHA_TIMEOUT_SECONDS = 30
# Where a work's page gives its PDF, in the order they are tried.
PDF_LINK_PATTERNS = (
    # The meta tag of the article's page, Sci-Hub's usual way.
    re.compile(r'citation_pdf_url["\']?\s*content=["\']([^"\']+)["\']', re.I),
    # The frame that shows the PDF.
    re.compile(r'<iframe[^>]+src=["\']([^"\']*?(?:pdf|files)[^"\']*?)["\']', re.I),
    re.compile(r'href=["\']([^"\']*?\.pdf[^"\']*?)["\']', re.I),
    re.compile(r'(https?://[^"\']*?/files/[^"\']*?)["\'\\]'),
    # The download button.
    re.compile(r'href=["\']([^"\']*?/download[^"\']*?)["\']', re.I),
)


class SeleniumSciHubFinder(DoiPdfFinder):

    def __init__(self):
        self.driver = None

    def find_pdf_urls_by_doi(self, dois: list[str]) -> dict[str, list[str]]:
        print(f"[SCIHUB] Buscando {len(dois)} PDFs en sci-hub...")
        try:
            if not self.driver:
                self._open_browser()
            pdf_urls = {}
            for number, doi in enumerate(dois, 1):
                print(f"  [{number}/{len(dois)}] {doi}...", end=" ", flush=True)
                pdf_url = self._pdf_url(doi)
                if pdf_url:
                    pdf_urls[doi] = [pdf_url]
                print("✓" if pdf_url else "✗")
            print(f"[SCIHUB] ✓ {len(pdf_urls)}/{len(dois)} PDFs encontrados")
            return pdf_urls
        except Exception as error:
            print(f"[SCIHUB] ✗ Error: {error}")
            return {}

    def close(self) -> None:
        if self.driver is None:
            return
        from selenium.common.exceptions import WebDriverException

        try:
            self.driver.quit()
        except WebDriverException as error:
            # The browser had already closed (it crashed, or the container stopped it).
            print(f"[SCIHUB] El navegador ya estaba cerrado: {error}")
        self.driver = None

    def _open_browser(self) -> None:
        from selenium import webdriver

        import browser_session

        print("[SCIHUB] Abriendo navegador...")
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        if browser_session.in_container():
            options.add_argument("--no-sandbox")
        self.driver = webdriver.Chrome(options=options)
        print("[SCIHUB] Abriendo sci-hub.su...")
        self.driver.get(SCI_HUB_URL)
        time.sleep(1)
        self._answer_captcha()

    def _answer_captcha(self) -> None:
        """Click "No" in the "Are you a robot?" question, when the page shows it, and wait for it to go."""
        from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions
        from selenium.webdriver.support.ui import WebDriverWait

        try:
            if CAPTCHA_TAG not in self.driver.page_source:
                return
            print("[SCIHUB] Resolviendo CAPTCHA...")
            try:
                no_button = self.driver.find_element(By.XPATH, "//div[@class='question']//div[@class='answer']")
                self.driver.execute_script("arguments[0].click();", no_button)
            except NoSuchElementException:
                self.driver.execute_script("document.querySelector('.question .answer')?.click()")
            time.sleep(0.5)
            try:
                WebDriverWait(self.driver, CAPTCHA_TIMEOUT_SECONDS).until(
                    expected_conditions.invisibility_of_element_located((By.TAG_NAME, CAPTCHA_TAG)))
                print("[SCIHUB] ✓ CAPTCHA resuelto")
            except TimeoutException:
                print("[SCIHUB] ⚠ CAPTCHA timeout")
            time.sleep(0.3)
        except WebDriverException as error:
            print(f"[SCIHUB] ⚠ Error: {error}")

    def _pdf_url(self, doi: str) -> str | None:
        """The address of the work's PDF, or None when Sci-Hub doesn't have it."""
        from selenium.common.exceptions import WebDriverException

        try:
            self.driver.get(SCI_HUB_URL + quote(doi, safe=":/"))
            time.sleep(0.3)
            if CAPTCHA_TAG in self.driver.page_source:
                self._answer_captcha()
                time.sleep(1.5)
            page = self.driver.page_source
        except WebDriverException:
            return None
        link = pdf_link_in_page(page)
        # Without a link to the PDF, Sci-Hub doesn't have the work (the page itself used to be returned,
        # and then failed to download and counted as found).
        return absolute_url(link) if link else None


def pdf_link_in_page(page: str) -> str | None:
    for pattern in PDF_LINK_PATTERNS:
        match = pattern.search(page)
        if match:
            return match.group(1)
    return None


def absolute_url(link: str) -> str:
    """Sci-Hub sometimes gives relative links ("/storage/...pdf#view=FitH&amp;...")."""
    return urldefrag(urljoin(SCI_HUB_URL, html.unescape(link))).url
