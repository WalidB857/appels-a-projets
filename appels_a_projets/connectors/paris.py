"""
Paris.fr connector - HTML scraping.
Source: https://www.paris.fr/pages/repondre-a-un-appel-a-projets-5412

Scrapes the "Appels à projets" page from the City of Paris website.
"""

import logging
import re
import time
import io
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .base import BaseConnector, RawAAP, save_raw_dataset
from ..utils.pdf_extractor import PdfExtractor


@dataclass
class ParisConfig:
    """Configuration for Paris scraper."""
    base_url: str = "https://www.paris.fr/appels-a-projets"
    timeout: int = 30
    user_agent: str = "AAP-Watch/1.0 (contact@example.com)"


class ParisConnector(BaseConnector):
    """
    Connector for Paris.fr AAP listings.
    """
    
    source_id = "paris_fr"
    source_name = "Ville de Paris"
    
    def __init__(self, config: ParisConfig | None = None):
        super().__init__()
        self.config = config or ParisConfig()
        self.base_url = self.config.base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.config.user_agent,
        })
        self.pdf_extractor = PdfExtractor()
    
    def fetch_raw(self) -> BeautifulSoup:
        """
        Fetch the main listing page.
        Returns a BeautifulSoup object.
        """
        self.logger.info(f"Fetching {self.base_url}...")
        try:
            response = self.session.get(self.base_url, timeout=self.config.timeout)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch Paris page: {e}")
            raise

    def parse(self, soup: BeautifulSoup) -> list[RawAAP]:
        """
        Parse the HTML page to extract AAPs.
        """
        aaps = []
        
        # Find all cards in the new layout
        cards = soup.find_all('a', class_='paris-card')
        
        seen_urls = set()
        
        for card in cards:
            href = card.get('href', '')
            if not href:
                continue
                
            url_source = urljoin("https://www.paris.fr", href)
            
            if url_source in seen_urls:
                continue

            # Extract title
            title_elem = card.find(class_='paris-card-title')
            titre = title_elem.get_text(strip=True) if title_elem else "Sans titre"

            # Filter out generic service pages if they don't look like AAPs
            format_elem = card.find(class_='paris-card-format')
            format_text = format_elem.get_text(strip=True).lower() if format_elem else ""
            
            # If it's marked as "Service" and title doesn't explicitly say "Appel à projets", skip it
            # (e.g. "Les appels à projets de la Ville de Paris" which is a landing page)
            if "service" in format_text and "appel à projets" not in titre.lower():
                continue

            # Extract date from card text
            # e.g. "Jusqu'au 11/02/2026" or "Du 19/12/2025 au 02/02/2026"
            date_elem = card.find(class_='paris-card-text')
            date_text = date_elem.get_text(strip=True) if date_elem else ""
            date_limite = self._parse_date(date_text)

            # Resume is not really on the card, maybe just the date text
            resume = None

            try:
                aap = self._parse_item(url_source, titre, date_limite, resume)
                if aap:
                    aaps.append(aap)
                    seen_urls.add(url_source)
            except Exception as e:
                self.logger.warning(f"Error parsing item {url_source}: {e}")
                continue
                
        return aaps

    def _parse_date(self, date_text: str) -> str | None:
        """Parse date string from card text."""
        if not date_text:
            return None
        # Extract all dates
        dates = re.findall(r'\d{2}/\d{2}/\d{4}', date_text)
        if dates:
            try:
                # Usually the last date is the deadline
                date_str = dates[-1]
                return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
            except ValueError:
                pass
        return None

    def _parse_item(self, url_source: str, titre: str, date_limite: str | None, resume: str | None) -> RawAAP | None:
        if not titre or len(titre) < 5:
            return None
            
        # --- Enrichment: Fetch details and PDF ---
        description = ""
        pdf_text = ""
        pdf_filename = None
        
        try:
            # Be polite
            time.sleep(0.5)
            
            self.logger.info(f"Fetching details for {url_source}")
            resp = self.session.get(url_source, timeout=self.config.timeout)
            resp.raise_for_status()
            detail_soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Extract description
            main_content = detail_soup.find('main') or detail_soup.find('div', class_='content') or detail_soup.find('div', class_='main-container')
            if main_content:
                # Remove scripts and styles
                for script in main_content(["script", "style"]):
                    script.decompose()
                description = main_content.get_text(" ", strip=True)
            
            # Handle PDFs
            best_pdf_url = self._get_best_pdf_url(detail_soup, url_source)
            if best_pdf_url:
                self.logger.info(f"Found PDF, extracting text: {best_pdf_url}")
                pdf_text = self._extract_pdf_text(best_pdf_url)
                pdf_filename = best_pdf_url.split('/')[-1]
                
        except Exception as e:
            self.logger.warning(f"Failed to fetch details for {url_source}: {e}")

        # Concatenate info for HTML enrichment
        enrich_txt_html = f"TITRE: {titre}\n\nRESUME: {resume or ''}\n\nDESCRIPTION: {description}"

        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            date_limite=date_limite,
            organisme='Ville de Paris',
            resume=resume,
            perimetre_geo='Paris (75)',
            enrich_txt_html=enrich_txt_html,
            enrich_txt_pdf=pdf_text,
            pdf_filename=pdf_filename
        )

    def _get_best_pdf_url(self, soup: BeautifulSoup, base_url: str) -> str | None:
        """
        Find the best PDF file.
        Priority:
        1. PDF with 'reglement' in text or filename.
        2. Largest PDF file.
        """
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
        if not pdf_links:
            return None
            
        reglement_links = []
        all_links = []
        
        # Regex for "reglement" with variations (accents, case)
        regex_reglement = re.compile(r'r[eéè]glement', re.IGNORECASE)
        
        for link in pdf_links:
            href = link.get('href')
            if not href:
                continue
            full_url = urljoin(base_url, href)
            text = link.get_text(" ", strip=True)
            
            if full_url not in all_links:
                all_links.append(full_url)
            
            if regex_reglement.search(text) or regex_reglement.search(href):
                if full_url not in reglement_links:
                    reglement_links.append(full_url)
        
        def get_largest(urls):
            largest_size = 0
            largest_url = None
            for url in urls:
                try:
                    head = self.session.head(url, timeout=5, allow_redirects=True)
                    if 'Content-Length' in head.headers:
                        size = int(head.headers['Content-Length'])
                        if size > largest_size:
                            largest_size = size
                            largest_url = url
                except Exception:
                    continue
            return largest_url

        # 1. Try reglement candidates
        if reglement_links:
            best = get_largest(reglement_links)
            if best:
                return best
                
        # 2. Fallback to largest of all
        return get_largest(all_links)

    def _extract_pdf_text(self, pdf_url: str) -> str:
        """Download PDF and extract text."""
        try:
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            return self.pdf_extractor.extract(response.content, filename=pdf_url.split('/')[-1])
            
        except Exception as e:
            self.logger.warning(f"Failed to extract text from PDF {pdf_url}: {e}")
            return ""

    def _extract_with_ocr(self, pdf_bytes: bytes) -> str:
        """Deprecated: Use PdfExtractor instead."""
        return self.pdf_extractor._extract_with_ocr(pdf_bytes)


def main():
    """Test the connector."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    connector = ParisConnector()
    try:
        aaps = connector.run()
        print(f"\nFound {len(aaps)} AAPs")
        
        # Use standardized saver
        save_raw_dataset(aaps, "paris")

    except Exception as e:
        print(f"Failed to run connector: {e}")

if __name__ == "__main__":
    main()
