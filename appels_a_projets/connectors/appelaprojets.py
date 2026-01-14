"""
Appel à Projets.org connector - HTML scraping with pagination.
Source: https://www.appelaprojets.org/appelprojet

Plateforme d'appels à projets avec pagination par offset.
Pagination observée :
- page 1 : https://www.appelaprojets.org/appelprojet
- page 2 : https://www.appelaprojets.org/appelprojet/9
- page 3 : https://www.appelaprojets.org/appelprojet/18
...

Note: le listing ne contient qu'un extrait. Pour récupérer tout le texte,
ce connecteur peut visiter chaque page détail (`fetch_details=True`).
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawAAP, save_raw_dataset

logger = logging.getLogger(__name__)


@dataclass
class AppelAProjetsConfig:
    """Configuration for Appel à Projets.org scraper."""

    base_url: str = "https://www.appelaprojets.org"
    list_url: str = "https://www.appelaprojets.org/appelprojet"
    timeout: int = 30
    max_pages: int = 10  # safety limit
    page_step: int = 9  # pagination offset step: 1, 9, 18, 27, ...
    fetch_details: bool = True  # récupérer le texte complet depuis les pages détail


class AppelAProjetsConnector(BaseConnector):
    """Connector for Appel à Projets.org (listing + optional detail scraping)."""

    source_id = "appelaprojets"
    source_name = "Appel à Projets.org"

    def __init__(self, config: AppelAProjetsConfig | None = None):
        super().__init__()
        self.config = config or AppelAProjetsConfig()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            }
        )

    def fetch_raw(self) -> list[BeautifulSoup]:
        """Fetch listing pages with robust offset pagination.

        Le site accepte des offsets variables (ex: /9, /10, /18...).
        Pour éviter de s'arrêter trop tôt, on :
        - itère sur start_at = 1, 9, 18, 27, ... (pas=9)
        - déduplique sur les URLs détectées dans le HTML
        - stop seulement après `max_empty_pages` pages consécutives sans nouveaux items.
        """

        pages: list[BeautifulSoup] = []
        seen_urls: set[str] = set()

        start_at = 1
        empty_pages = 0
        max_empty_pages = 2

        for page_idx in range(1, self.config.max_pages + 1):
            page_url = self.config.list_url if start_at <= 1 else f"{self.config.list_url}/{start_at}"
            self.logger.info(f"Fetching page {page_idx} (start_at={start_at}): {page_url}")

            try:
                response = self.session.get(page_url, timeout=self.config.timeout)
                response.raise_for_status()
            except requests.RequestException as e:
                self.logger.warning(f"Failed to fetch page {page_idx} ({page_url}): {e}")
                break

            soup = BeautifulSoup(response.content, "html.parser")
            content_divs = soup.select("div.projet > div.content")

            if not content_divs:
                self.logger.info(f"No listing blocks found at start_at={start_at}")
                empty_pages += 1
            else:
                # détecter si la page apporte de nouveaux items
                new_count = 0
                for div in content_divs:
                    link_tag = div.find("a", class_=lambda c: c and "btn" in c)
                    href = link_tag.get("href") if link_tag else None
                    if not href:
                        continue
                    url = urljoin(self.config.base_url, href)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        new_count += 1

                if new_count == 0:
                    empty_pages += 1
                    self.logger.info(
                        f"No new items at start_at={start_at} (seen={len(seen_urls)}). empty_pages={empty_pages}/{max_empty_pages}"
                    )
                else:
                    empty_pages = 0

                pages.append(soup)

            if empty_pages >= max_empty_pages:
                self.logger.info("Stopping pagination: too many consecutive pages without new items")
                break

            start_at += self.config.page_step

        self.logger.info(f"Fetched {len(pages)} pages total")
        return pages

    def parse(self, pages: list[BeautifulSoup]) -> list[RawAAP]:
        """Parse all pages and extract AAPs from `div.projet > div.content`."""

        aaps: list[RawAAP] = []
        seen_urls: set[str] = set()

        for page_idx, soup in enumerate(pages, start=1):
            self.logger.info(f"Parsing page {page_idx}...")

            items = soup.select("div.projet > div.content")
            if not items:
                self.logger.warning(f"No items found on page {page_idx} with selector div.projet > div.content")
                continue

            for item in items:
                try:
                    aap = self._parse_item(item)
                    if not aap:
                        continue
                    if aap.url_source in seen_urls:
                        continue

                    # Enrich with full detail text
                    if self.config.fetch_details:
                        self._enrich_with_details(aap)

                    aaps.append(aap)
                    seen_urls.add(aap.url_source)
                except Exception as e:
                    self.logger.warning(f"Failed to parse item on page {page_idx}: {e}")

        self.logger.info(f"Parsed {len(aaps)} AAPs from {self.source_name}")
        save_raw_dataset(aaps, self.source_id)
        return aaps

    def _parse_item(self, content_div: BeautifulSoup) -> RawAAP | None:
        """Parse a single AAP item from `<div class=\"content\">` in the listing."""

        titre_tag = content_div.select_one("h3")
        if not titre_tag:
            return None
        titre = self._clean_html(titre_tag.get_text(strip=True))
        if not titre:
            return None

        # URL: bouton (class contains btn)
        link_tag = content_div.find("a", class_=lambda c: c and "btn" in c)
        href = link_tag.get("href") if link_tag else None
        if not href:
            return None
        url_source = urljoin(self.config.base_url, href)

        # Listing summary (keep as resume hint)
        resume = ""
        infos_div = content_div.select_one("div.infos")
        if infos_div:
            resume = self._clean_html(infos_div.get_text(" ", strip=True))

        # Deadline
        date_limite = None
        date_tag = content_div.select_one("strong.date")
        if date_tag:
            date_limite = self._parse_french_date(date_tag.get_text(" ", strip=True))

        # Defaults for listing-only scraping
        organisme = self.source_name
        date_publication = None
        tags: list[str] = []
        perimetre_geo = "National"

        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            organisme=organisme,
            date_limite=date_limite,
            date_publication=date_publication,
            resume=resume or None,
            # description filled by detail page if enabled
            description=None,
            tags=tags,
            perimetre_geo=perimetre_geo,
        )

    def fetch_detail(self, url: str) -> dict:
        """Fetch a detail page to extract full text and extra fields."""

        try:
            r = self.session.get(url, timeout=self.config.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            self.logger.warning(f"Failed to fetch detail page {url}: {e}")
            return {}

        soup = BeautifulSoup(r.text, "html.parser")

        details: dict = {}

        # Try several containers (site can evolve)
        candidates = [
            "div#contenu",  # common id on some themes
            "main",
            "article",
            "div.projet",
            "div.content",
        ]

        text_parts: list[str] = []
        for sel in candidates:
            node = soup.select_one(sel)
            if not node:
                continue
            txt = node.get_text("\n", strip=True)
            txt = self._clean_html(txt)
            if txt and len(txt) > 200:
                text_parts.append(txt)
                break

        if not text_parts:
            # last resort: entire page text (avoid empty content)
            txt = self._clean_html(soup.get_text("\n", strip=True))
            if txt:
                text_parts.append(txt)

        full_text = text_parts[0] if text_parts else ""
        details["description"] = full_text

        # candidature url
        candid_link = soup.select_one("a[href*='candid'], a[href*='inscription'], a[href*='form'], a.btn")
        if candid_link:
            href = candid_link.get("href")
            if href and not href.startswith("mailto:"):
                details["url_candidature"] = urljoin(self.config.base_url, href)

        # email
        mail = soup.select_one("a[href^='mailto:']")
        if mail:
            email = mail.get("href", "").replace("mailto:", "").strip()
            details["email_contact"] = email or None

        # deadline: in case more explicit in detail
        if not details.get("date_limite"):
            m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", full_text)
            if m:
                details["date_limite"] = self._parse_french_date(m.group(0))

        return details

    def _enrich_with_details(self, aap: RawAAP) -> None:
        """Populate description/enrichment fields from detail page."""

        details = self.fetch_detail(aap.url_source)
        if not details:
            return

        if details.get("description"):
            # keep FULL text (requirement)
            aap.description = details["description"]

        if details.get("url_candidature"):
            aap.url_candidature = details["url_candidature"]

        if details.get("email_contact"):
            aap.email_contact = details["email_contact"]

        if details.get("date_limite") and not aap.date_limite:
            aap.date_limite = details["date_limite"]

        # LLM enrichment input: include full text
        aap.enrich_txt_html = (
            f"TITRE: {aap.titre}\n"
            f"URL: {aap.url_source}\n"
            f"DATE_LIMITE: {aap.date_limite or ''}\n\n"
            f"RESUME: {aap.resume or ''}\n\n"
            f"DESCRIPTION: {aap.description or ''}"
        )

    def _parse_french_date(self, date_str: str) -> str | None:
        """Parse French date format to YYYY-MM-DD.

        Accepts text containing a date, e.g. "Expire le 15/01/2026".
        """

        if not date_str:
            return None

        match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_str)
        if not match:
            return None

        day, month, year = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day))
        except ValueError:
            self.logger.warning(f"Could not parse date: {date_str}")
            return None

        return dt.strftime("%Y-%m-%d")

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""

        if not text:
            return ""

        text = unescape(text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


def main():
    """Test the connector."""

    logging.basicConfig(level=logging.INFO)

    # Par défaut on teste sur plus de pages ; ajuster si besoin
    config = AppelAProjetsConfig(max_pages=10, fetch_details=True)
    connector = AppelAProjetsConnector(config)

    print("🔍 Fetching Appel à Projets.org...")
    aaps = connector.run()

    print(f"\n{'='*60}")
    print(f"Found {len(aaps)} AAPs")
    print(f"{'='*60}\n")

    for aap in aaps[:5]:
        print(f"- {aap.titre}")
        print(f"  📅 Deadline: {aap.date_limite or 'Inconnue'}")
        print(f"  🏢 {aap.organisme or 'N/A'}")
        print(f"  🔗 {aap.url_source}\n")


if __name__ == "__main__":
    main()
