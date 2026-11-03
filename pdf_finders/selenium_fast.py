"""Sci-hub finder rápido - click manual en CAPTCHA, optimizado para velocidad"""
import os
import time
import html as html_lib
from urllib.parse import quote, urldefrag, urljoin

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from pdf_finders.base import DoiPdfFinder


class SeleniumSciHubFinder(DoiPdfFinder):
    """Encuentra PDFs en sci-hub - optimizado para velocidad"""

    def __init__(self):
        self.driver = None

    def find_pdf_urls_by_doi(self, dois: list[str]) -> dict[str, list[str]]:
        if not SELENIUM_AVAILABLE:
            return {}

        print(f"[SCIHUB] Buscando {len(dois)} PDFs en sci-hub...")

        try:
            if not self.driver:
                self._init_browser()

            results = {}
            for i, doi in enumerate(dois, 1):
                print(f"  [{i}/{len(dois)}] {doi}...", end=" ", flush=True)
                pdf_url = self._absolute_url(self._get_pdf(doi))
                if pdf_url:
                    results[doi] = [pdf_url]
                    print("✓")
                else:
                    print("✗")

            print(f"[SCIHUB] ✓ {len(results)}/{len(dois)} PDFs encontrados")
            return results
        except Exception as e:
            print(f"[SCIHUB] ✗ Error: {e}")
            return {}

    def _init_browser(self):
        """Abre navegador"""
        print("[SCIHUB] Abriendo navegador...")
        try:
            opts = webdriver.ChromeOptions()
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-extensions")
            opts.add_argument("--disable-plugins")
            # Inside a container (docker-compose.prod.yml) Chrome can't use its own sandbox.
            if os.environ.get("CHROME_IN_CONTAINER"):
                opts.add_argument("--no-sandbox")
            self.driver = webdriver.Chrome(options=opts)
        except:
            self.driver = webdriver.Firefox()

        print("[SCIHUB] Abriendo sci-hub.su...")
        self.driver.get("https://sci-hub.su/")
        time.sleep(1)

        # Resolver CAPTCHA si aparece
        self._resolve_captcha()

    def _resolve_captcha(self):
        """Resuelve CAPTCHA si aparece"""
        try:
            html = self.driver.page_source
            if "altcha-widget" not in html:
                return

            print("[SCIHUB] Resolviendo CAPTCHA...")

            try:
                no_button = self.driver.find_element(By.XPATH, "//div[@class='question']//div[@class='answer']")
                self.driver.execute_script("arguments[0].click();", no_button)
            except:
                self.driver.execute_script("document.querySelector('.question .answer')?.click()")

            time.sleep(0.5)
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.invisibility_of_element_located((By.TAG_NAME, "altcha-widget"))
                )
                print("[SCIHUB] ✓ CAPTCHA resuelto")
            except:
                print("[SCIHUB] ⚠ CAPTCHA timeout")

            time.sleep(0.3)
        except Exception as e:
            print(f"[SCIHUB] ⚠ Error: {e}")

    def _absolute_url(self, url: str | None) -> str | None:
        """Sci-hub a veces da enlaces relativos ("/storage/...pdf#view=FitH&amp;...")."""
        if not url:
            return None
        url = urljoin("https://sci-hub.su/", html_lib.unescape(url))
        return urldefrag(url).url

    def _get_pdf(self, doi: str) -> str | None:
        """Obtiene PDF rápidamente"""
        if not self.driver:
            return None

        encoded = quote(doi, safe=":/")
        url = f"https://sci-hub.su/{encoded}"

        try:
            self.driver.get(url)
            time.sleep(0.3)

            html = self.driver.page_source

            # Si CAPTCHA aparece, resolver
            if "altcha-widget" in html:
                self._resolve_captcha()
                time.sleep(1.5)
                html = self.driver.page_source

            # Buscar PDF
            import re

            # Buscar en meta tag citation_pdf_url (método principal de sci-hub)
            m = re.search(r'citation_pdf_url["\']?\s*content=["\']([^"\']+)["\']', html, re.I)
            if m:
                pdf_url = m.group(1)
                if not pdf_url.startswith('http'):
                    pdf_url = 'https://sci-hub.su' + pdf_url
                return pdf_url

            # Buscar frame de descarga
            m = re.search(r'<iframe[^>]+src=["\']([^"\']*?)["\']', html, re.I)
            if m:
                iframe_url = m.group(1)
                if 'pdf' in iframe_url.lower() or 'files' in iframe_url.lower():
                    return iframe_url

            # Buscar enlaces directos
            m = re.search(r'href=["\']([^"\']*?\.pdf[^"\']*?)["\']', html, re.I)
            if m:
                return m.group(1)

            # Buscar /files/
            m = re.search(r'(https?://[^"\']*?/files/[^"\']*?)["\'\\]', html)
            if m:
                return m.group(1)

            # Buscar botón de descarga
            m = re.search(r'href=["\']([^"\']*?/download[^"\']*?)["\']', html, re.I)
            if m:
                return m.group(1)

            # Sin enlace al PDF, Sci-Hub no tiene la obra (antes se devolvía la página,
            # que luego fallaba al descargar y contaba como "encontrado").
            return None

        except:
            return None

    def __del__(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
