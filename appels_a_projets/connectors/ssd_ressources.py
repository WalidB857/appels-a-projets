import logging
import re
import time
import random
import hashlib
import unicodedata
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawAAP, save_raw_dataset
from ..utils.pdf_extractor import PdfExtractor

logger = logging.getLogger(__name__)


@dataclass
class SSDRessourcesConfig:
    base_url: str = "https://ressources.seinesaintdenis.fr/"
    max_pages: int = 5
    timeout: int = 20
    use_selenium: bool = True
    min_delay: float = 1.0  # Délai minimum entre requêtes (secondes)
    max_delay: float = 3.0  # Délai maximum entre requêtes (secondes)
    output_dir: Path = Path("data/ssd_ressources/content")  # Dossier de sortie
    selenium_headless: bool = True
    selenium_anti_bot_wait_s: float = 4.0
    selenium_render_wait_s: float = 2.0
    selenium_page_wait_timeout_s: float = 15.0


class SSDRessourcesConnector(BaseConnector):
    source_id = "ssd_ressources"
    source_name = "Ressources Seine-Saint-Denis"

    def __init__(self, config: SSDRessourcesConfig | None = None):
        self.config = config or SSDRessourcesConfig()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AAP-Watch/1.0)"
        })
        self.pdf_extractor = PdfExtractor()
        self._driver = None

    def __enter__(self):
        if self._driver is None and self.config.use_selenium:
            self._driver = self._create_selenium_driver()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._close_driver()

    def _close_driver(self) -> None:
        if self._driver is None:
            return
        try:
            self._driver.quit()
        except Exception:
            pass
        self._driver = None

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        """Normalise une chaîne pour matching insensible aux accents/casse."""
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        return text.lower()

    def _create_selenium_driver(self):
        """Crée un driver Selenium Chrome robuste (anti-bot + Windows)."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        if self.config.selenium_headless:
            chrome_options.add_argument("--headless=new")

        # Recommandé par ChromeDriver récents
        chrome_options.add_argument("--remote-debugging-pipe")

        # Stabilité + éviter first run
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-features=ChromeWhatsNewUI")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1400,900")

        # Anti-détection légère
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        )

        # Profil temporaire
        profile_dir = Path("data/ssd_ressources/selenium_profiles") / f"profile-{int(time.time() * 1000)}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
        chrome_options.add_argument("--profile-directory=Default")

        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        return driver

    def _get_driver(self):
        if self._driver is None:
            self._driver = self._create_selenium_driver()
        return self._driver

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        allow_redirects: bool = True,
        max_attempts: int = 4,
        backoff_base_s: float = 1.0,
        **kwargs,
    ) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                    **kwargs,
                )
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                sleep_s = backoff_base_s * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                logger.warning(f"HTTP {method} failed (attempt {attempt}/{max_attempts}) url={url}: {e}. sleep={sleep_s:.2f}s")
                time.sleep(sleep_s)
        assert last_exc is not None
        raise last_exc

    def _is_probably_antibot_page(self, soup: BeautifulSoup) -> bool:
        """Heuristique: détecte la page 'Vous allez être redirigé' / contenu vide."""
        try:
            title = (soup.title.string or '').strip() if soup.title else ''
        except Exception:
            title = ''

        text = soup.get_text(' ', strip=True).lower()

        # indicateurs connus sur ce site
        if 'vous allez' in text and 'redirig' in text:
            return True

        # titre générique + peu de contenu
        if title == 'Seine-Saint-Denis' and len(text) < 800:
            return True

        # pas d'article = souvent pas la page finale
        if soup.select_one('article') is None and len(text) < 800:
            return True

        return False

    def _selenium_get_soup(self, url: str) -> BeautifulSoup:
        """Charge une URL via Selenium et renvoie la soup.

        Robustesse:
        - retry avec backoff sur net::ERR_CONNECTION_RESET
        - restart driver entre tentatives
        - attend anti-bot + rendu
        - vérifie qu'on n'est pas sur page anti-bot
        """
        last_exc: Exception | None = None

        for attempt in range(1, 4):
            driver = self._get_driver()
            try:
                driver.get(url)

                time.sleep(self.config.selenium_anti_bot_wait_s)
                time.sleep(self.config.selenium_render_wait_s)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                if self._is_probably_antibot_page(soup):
                    raise RuntimeError('Anti-bot page detected (still redirecting / empty content)')

                return soup

            except Exception as e:
                last_exc = e
                logger.warning(f"Selenium fetch failed (attempt {attempt}/3). url={url} err={e}")

                # restart driver before next attempt
                self._close_driver()

                # backoff
                sleep_s = (1.0 * (2 ** (attempt - 1))) + random.uniform(0, 0.4)
                time.sleep(sleep_s)

        assert last_exc is not None
        raise last_exc

    def _sync_cookies_from_driver_to_session(self) -> None:
        """Copie les cookies Selenium -> requests.Session pour télécharger PDFs avec la même session anti-bot."""
        try:
            driver = self._get_driver()
            for c in driver.get_cookies():
                # Selenium: {'name','value','domain','path',...}
                self.session.cookies.set(c.get('name'), c.get('value'), domain=c.get('domain'), path=c.get('path'))
        except Exception as e:
            logger.debug(f"Could not sync cookies from Selenium to requests: {e}")

    def fetch_raw(self) -> list[BeautifulSoup]:
        """Récupère les pages HTML de la liste des ressources."""
        if not self.config.use_selenium:
            return self._fetch_with_requests()

        pages: list[BeautifulSoup] = []
        try:
            for i in range(self.config.max_pages):
                offset = i * 6
                url = f"{self.config.base_url}?debut_ressources={offset}"
                logger.info(f"Fetching listing page with Selenium: {url}")
                soup = self._selenium_get_soup(url)
                pages.append(soup)
        except Exception as e:
            logger.error(f"Erreur Selenium: {e}")
            logger.info("Fallback sur requests...")
            return self._fetch_with_requests()

        return pages

    def _fetch_with_requests(self) -> list[BeautifulSoup]:
        pages: list[BeautifulSoup] = []
        for i in range(self.config.max_pages):
            offset = i * 6
            url = f"{self.config.base_url}?debut_ressources={offset}"
            logger.info(f"Fetching listing page: {url}")
            try:
                resp = self._request_with_retries("GET", url, timeout=self.config.timeout)
                pages.append(BeautifulSoup(resp.text, "html.parser"))
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
        return pages

    def _looks_like_aap(self, text: str) -> bool:
        """Filtre pragmatique: conserve uniquement les pages qui parlent d'AAP/AMI/etc."""
        norm = self._normalize_for_match(text)

        # Mots clés "AAP" (on peut étoffer)
        keywords = [
            r"appel\s+a\s+projets?",
            r"appel\s+a\s+candidatures",
            r"appel\s+a\s+manifestation\s+d[' ]interet",
            r"\bami\b",
            r"\baap\b",
            r"depot\s+de\s+candidature",
            r"dossier\s+de\s+candidature",
            r"date\s+limite",
            r"date\s+de\s+cloture",
            r"calendrier\s+de\s+l[' ]appel",
            r"selection\s+des\s+projets",
            r"porteurs?\s+de\s+projet",
            r"criteres?\s+de\s+selection",
            r"conditions?\s+d[' ]eligibilite",
            r"subvention",
            r"aide\s+financiere",
            r"montant\s+de\s+l[' ]aide",
            r"laureats?",
            r"projets?\s+retenus",
        ]

        return any(re.search(pat, norm) for pat in keywords)

    def parse(self, pages: list[BeautifulSoup]) -> list[RawAAP]:
        aaps: list[RawAAP] = []
        for i, soup in enumerate(pages):
            colonedroite = soup.select_one("#colonedroite") or soup.select_one(".liste_ressources")
            if not colonedroite:
                logger.warning(f"Page {i+1}: Section #colonedroite introuvable")
                continue

            items = colonedroite.select("article[role='article']")
            logger.info(f"Page {i+1}: {len(items)} articles trouvés dans #colonedroite")

            for item in items:
                try:
                    aap = self._parse_item(item)
                    if aap:
                        aaps.append(aap)
                except Exception as e:
                    logger.error(f"Error parsing item in {self.source_id}: {e}")

        logger.info(f"Extracted {len(aaps)} items from {self.source_name}")

        # Sauvegarde standardisée (metadata.json + content/*.txt) compatible scripts/enrich_dataset.py
        save_raw_dataset(aaps, self.source_id)

        # On ferme le driver après avoir fait listing + détails
        self._close_driver()
        return aaps

    def _pick_primary_pdf(self, pdf_sizes: dict[str, int]) -> tuple[str, int] | None:
        if not pdf_sizes:
            return None

        # 1) Priorité: PDF contenant 'reglement' ou 'reglements' (insensible accents/casse)
        # NB: _normalize_for_match enlève aussi les accents, donc 'règlement(s)' match.
        reglement_pat = re.compile(r"\breglements?\b", re.IGNORECASE)
        reglement_candidates: list[tuple[str, int]] = []

        for url, size in pdf_sizes.items():
            norm = self._normalize_for_match(url)
            if reglement_pat.search(norm):
                reglement_candidates.append((url, size))

        if reglement_candidates:
            return max(reglement_candidates, key=lambda x: x[1])

        return max(pdf_sizes.items(), key=lambda x: x[1])

    def _looks_like_pdf(self, content: bytes, content_type: str | None) -> bool:
        if content_type and 'pdf' in content_type.lower():
            return True
        # Signature magique PDF
        return content.startswith(b'%PDF-')

    def _download_pdf_bytes(self, pdf_url: str) -> bytes:
        """Télécharge un PDF en gérant le cas anti-bot (HTML renvoyé) + resets réseau."""
        # A ce stade, on a déjà visité la page détail via Selenium -> cookies utiles.
        if self.config.use_selenium:
            self._sync_cookies_from_driver_to_session()

        # Délai léger pour réduire les resets (serveur sensible)
        time.sleep(random.uniform(0.8, 1.6))

        try:
            resp = self._request_with_retries("GET", pdf_url, timeout=30)
            ctype = resp.headers.get('content-type')
            if self._looks_like_pdf(resp.content[:1024], ctype):
                return resp.content

            head = resp.content[:32]
            logger.warning(
                "PDF download did not return a PDF (likely anti-bot HTML). "
                f"url={pdf_url} content-type={ctype} head={head!r}"
            )
            return b""
        except Exception as e:
            logger.warning(f"Direct PDF download failed for {pdf_url}: {e}")
            return b""

    def _parse_item(self, item: BeautifulSoup) -> RawAAP | None:
        theme_tag = item.find("p", class_="theme")
        theme = theme_tag.get_text(strip=True) if theme_tag else None

        h4 = item.find("h4")
        if not h4:
            return None

        a_tag = h4.find("a")
        if not a_tag or not a_tag.get("href"):
            return None

        title = a_tag.get_text(" ", strip=True)
        href = a_tag["href"]

        date_publication = None
        time_tag = item.find("time", attrs={"datetime": True})
        if time_tag:
            date_str = time_tag["datetime"]
            try:
                from datetime import datetime

                date_publication = datetime.fromisoformat(date_str.split()[0]).strftime("%Y-%m-%d")
            except Exception as e:
                logger.warning(f"Failed to parse date {date_str}: {e}")

        url_source = urljoin(self.config.base_url, href) if not href.startswith("http") else href
        logger.info(f"🔗 Scraping détail : {url_source} (Thème: {theme}, Date: {date_publication})")

        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        time.sleep(delay)

        # Page détail via Selenium shared (avec retry)
        try:
            detail_soup = self._selenium_get_soup(url_source)
        except Exception as e:
            logger.warning(f"Failed to fetch detail page with Selenium {url_source}: {e}")

            # fallback requests pour sauver au moins le HTML (même si anti-bot)
            try:
                resp = self._request_with_retries('GET', url_source, timeout=self.config.timeout)
                detail_soup = BeautifulSoup(resp.text, 'html.parser')
            except Exception as e2:
                logger.error(f"Fallback requests failed for {url_source}: {e2}")
                return RawAAP(
                    titre=title,
                    url_source=url_source,
                    source_id=self.source_id,
                    description=title,
                    organisme="Département Seine-Saint-Denis",
                    date_publication=date_publication,
                )

        # HTML content
        main_content = None
        selectors = [
            "article > div.content",
            "article .content",
            "article .texte",
            ".texte",
            "article",
        ]
        for selector in selectors:
            main_content = detail_soup.select_one(selector)
            if main_content:
                break

        if not main_content:
            main_content = detail_soup.body

        description = title
        enrich_txt_html = ""
        if main_content:
            for tag in main_content(["script", "style", "iframe", "nav", "header", "footer", "aside"]):
                tag.decompose()
            for ajax_bloc in main_content.select(".ajaxbloc"):
                ajax_bloc.decompose()
            description = main_content.get_text("\n", strip=True)

            # Texte pour enrichissement LLM
            enrich_txt_html = f"TITRE: {title}\nURL: {url_source}\n\n{description}"

        # Filtre AAP: si le contenu ne mentionne pas d'AAP/AMI/etc, on rejette
        if not self._looks_like_aap(description):
            logger.info(f"⏭️ Skipping non-AAP page (filtered): {url_source}")
            return None

        # Emails + PDFs
        page_text = detail_soup.get_text(" ")
        emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", page_text)

        # PDFs
        pdf_links: list[str] = []
        pdf_sizes: dict[str, int] = {}

        docs_section = detail_soup.select_one(".docs")
        pdf_container = docs_section if docs_section else detail_soup

        for a in pdf_container.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue

            pdf_url = urljoin(url_source, href)
            pdf_links.append(pdf_url)

            # size from HTML
            parent_div = a.find_parent("div", class_="row")
            if parent_div:
                size_text = parent_div.get_text(" ", strip=True)
                size_match = re.search(r"([\d.]+)\s*(kio|Mio)", size_text, re.IGNORECASE)
                if size_match:
                    size_value = float(size_match.group(1))
                    unit = size_match.group(2).lower()
                    pdf_sizes[pdf_url] = int(size_value * 1024 * 1024) if unit == "mio" else int(size_value * 1024)
                    continue

            # fallback HEAD
            try:
                head_resp = self._request_with_retries("HEAD", pdf_url, timeout=5, allow_redirects=True)
                if "content-length" in head_resp.headers:
                    pdf_sizes[pdf_url] = int(head_resp.headers["content-length"])
            except Exception:
                pass

        if self.config.use_selenium:
            self._sync_cookies_from_driver_to_session()

        pdf_content = ""
        pdf_filename = None
        picked = self._pick_primary_pdf(pdf_sizes)
        if picked:
            primary_pdf_url, primary_pdf_size = picked
            logger.info(f"📄 Téléchargement du PDF principal: {primary_pdf_url} ({primary_pdf_size / 1024:.1f} KB)")

            try:
                pdf_bytes = self._download_pdf_bytes(primary_pdf_url)
                pdf_filename = primary_pdf_url.split("/")[-1]
                if pdf_bytes:
                    pdf_content = self.pdf_extractor.extract(pdf_bytes=pdf_bytes, filename=pdf_filename)
            except Exception as e:
                logger.warning(f"PDF extraction failed for {primary_pdf_url}: {e}")

        enriched_description = ""
        if theme:
            enriched_description += f"[Thème: {theme}]\n\n"
        enriched_description += description

        if emails:
            enriched_description += f"\n\n--- CONTACTS ---\n{', '.join(sorted(set(emails)))}"
        if pdf_links:
            enriched_description += "\n\n--- PIÈCES JOINTES ---\n" + "\n".join(sorted(set(pdf_links)))
        if pdf_content:
            enriched_description += f"\n\n--- CONTENU DU PDF PRINCIPAL ---\n{pdf_content}"

        aap = RawAAP(
            titre=title,
            url_source=url_source,
            source_id=self.source_id,
            description=enriched_description,
            organisme="Département Seine-Saint-Denis",
            date_publication=date_publication,
        )
        # Champs nécessaires pour save_raw_dataset + enrich_dataset
        aap.enrich_txt_html = enrich_txt_html
        aap.enrich_txt_pdf = pdf_content if pdf_content else None
        aap.pdf_filename = pdf_filename
        aap.email_contact = emails[0] if emails else None

        return aap


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with SSDRessourcesConnector() as connector:
        print("🔍 Démarrage du scraping manuel...")
        raw = connector.fetch_raw()
        items = connector.parse(raw)
        print(f"✅ Terminé : {len(items)} éléments trouvés.")
        for item in items[:5]:
            print(f"- {item.titre} ({item.url_source})")