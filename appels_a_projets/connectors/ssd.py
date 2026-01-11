"""
Seine-Saint-Denis (SSD) connector - HTML scraping.
Source: https://www.seine-saint-denis.gouv.fr/Actualites/Appels-a-projets

Scrapes the "Appels à projets" page from the Seine-Saint-Denis prefecture website.
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawAAP, save_raw_dataset
from ..utils.pdf_extractor import PdfExtractor


@dataclass
class SSDConfig:
    """Configuration for SSD scraper."""
    base_url: str = "https://www.seine-saint-denis.gouv.fr/Actualites/Appels-a-projets"
    max_pages: int = 3
    timeout: int = 30
    user_agent: str = "AAP-Watch/1.0 (contact@example.com)"


class SSDConnector(BaseConnector):
    """
    Connector for Seine-Saint-Denis AAP listings.
    """
    
    source_id = "ssd_pref"
    source_name = "Préfecture Seine-Saint-Denis"
    
    def __init__(self, config: SSDConfig | None = None):
        super().__init__()
        self.config = config or SSDConfig()
        self.base_url = self.config.base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.config.user_agent,
        })
        self.pdf_extractor = PdfExtractor()
    
    def fetch_raw(self) -> list[BeautifulSoup]:
        """
        Fetch listing pages.
        Returns a list of BeautifulSoup objects.
        """
        pages = []
        
        for page_num in range(self.config.max_pages):
            offset = page_num * 10
            if offset == 0:
                url = self.base_url
            else:
                url = f"{self.base_url}/(offset)/{offset}"
            
            self.logger.info(f"Fetching page {page_num + 1} (offset={offset})...")
            
            try:
                response = self.session.get(url, timeout=self.config.timeout)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check if content exists
                articles = soup.find_all(['div', 'li', 'article'], class_=re.compile(r'(item|article|news|appel)', re.I))
                links = soup.find_all('a', href=re.compile(r'Appels-a-projets/.+', re.I))
                
                if not articles and not links:
                    self.logger.info("No more content found.")
                    break
                
                pages.append(soup)
                time.sleep(1)  # Be polite
                
            except requests.RequestException as e:
                self.logger.error(f"Failed to fetch SSD page {page_num}: {e}")
                break
                
        return pages

    def _find_redirect_link(self, soup: BeautifulSoup, base_url: str) -> str | None:
        """Find a link with text like 'voir ici', 'retrouvez ici'."""
        patterns = [
            r'retrouvez.*?ici',
            r'voir.*?ici',
            r'présent.*?ici',
            r'cliquez.*?ici',
            r'consultez.*?ici'
        ]
        combined_pattern = "|".join(patterns)
        
        for a in soup.find_all('a', href=True):
            text = a.get_text(" ", strip=True)
            if re.search(combined_pattern, text, re.IGNORECASE):
                return urljoin(base_url, a['href'])
        return None

    def parse(self, pages: list[BeautifulSoup]) -> list[RawAAP]:
        """
        Parse the HTML pages to extract AAPs.
        """
        aaps = []
        seen_urls = set()
        
        for soup in pages:
            # Strategy 1: Article blocks
            items = soup.find_all(['div', 'article'], class_=re.compile(r'(item|article|news-item)', re.I))
            
            # Strategy 2: Links in main content
            if not items:
                main_content = soup.find('div', id=re.compile(r'(main|content|centre)', re.I))
                if main_content:
                    items = main_content.find_all('a', href=re.compile(r'Appels-a-projets/', re.I))
            
            for item in items:
                try:
                    aap = self._parse_item(item)
                    if aap and aap.url_source not in seen_urls:
                        # Filter out pagination links or base url
                        if 'offset' in aap.url_source or aap.url_source == self.base_url:
                            continue
                            
                        aaps.append(aap)
                        seen_urls.add(aap.url_source)
                except Exception as e:
                    self.logger.warning(f"Error parsing item: {e}")
                    continue
                
        return aaps

    def _parse_item(self, item) -> RawAAP | None:
        # Extract Title and URL
        if item.name == 'a':
            title_elem = item
            link_elem = item
            container = item.parent
        else:
            title_elem = item.find(['h2', 'h3', 'h4', 'a'])
            link_elem = item.find('a', href=True)
            container = item
        
        if not title_elem or not link_elem:
            return None
            
        titre = title_elem.get_text(strip=True)
        href = link_elem.get('href', '')
        url_source = urljoin(self.base_url, href)
        
        # Initialize variables
        resume = None
        email_contact = None
        date_limite = None
        description = ""
        pdf_text = ""
        pdf_filename = None
        
        # --- FETCH DETAILS ---
        try:
            # Check if it is a PDF directly
            is_pdf = any(url_source.lower().endswith(ext) for ext in ['.pdf'])
            
            if is_pdf:
                self.logger.info(f"Direct PDF link found: {url_source}")
                pdf_filename = url_source.split('/')[-1]
                # Download and extract PDF
                resp = self.session.get(url_source, timeout=self.config.timeout)
                resp.raise_for_status()
                pdf_text = self.pdf_extractor.extract(resp.content, filename=pdf_filename)
                
            else:
                # It's an HTML page
                # Be polite with the server
                time.sleep(0.2)
                
                detail_resp = self.session.get(url_source, timeout=self.config.timeout)
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                
                # Check for external content (redirects)
                external_url = self._find_redirect_link(detail_soup, url_source)
                external_soup = None
                
                if external_url:
                    self.logger.info(f"Following external link: {external_url}")
                    try:
                        ext_resp = self.session.get(external_url, timeout=self.config.timeout)
                        ext_resp.raise_for_status()
                        external_soup = BeautifulSoup(ext_resp.text, 'html.parser')
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch external content {external_url}: {e}")

                # Extract full text for enrichment
                main_content = detail_soup.select_one("#main") or detail_soup.select_one(".texte") or detail_soup.body
                if main_content:
                    # Remove scripts/styles
                    for s in main_content(["script", "style"]):
                        s.decompose()
                    description = main_content.get_text(" ", strip=True)
                
                if external_soup:
                    # Clean and append external content
                    ext_body = external_soup.body or external_soup
                    for s in ext_body(["script", "style"]):
                        s.decompose()
                    ext_text = ext_body.get_text(" ", strip=True)
                    description += f"\n\n[CONTENU EXTERNE SCRAPÉ: {external_url}]\n{ext_text}"
                
                # 1. Resume extraction
                # Strategy A: DSFR .fr-text--lead (New standard)
                lead = detail_soup.select_one(".fr-text--lead")
                if lead:
                    resume = lead.get_text(strip=True)
                
                # Strategy B: Legacy .chapo
                if not resume:
                    chapo = detail_soup.select_one(".chapo")
                    if chapo:
                        resume = chapo.get_text(strip=True)
                
                # Strategy C: First paragraph of main content
                if not resume:
                    # Try to find the main content area
                    main_col = detail_soup.select_one("#main .fr-col-md-8") or detail_soup.select_one(".texte")
                    if main_col:
                        first_p = main_col.find('p')
                        if first_p:
                            resume = first_p.get_text(strip=True)

                # Truncate if too long
                if resume and len(resume) > 500:
                    resume = resume[:497] + "..."
                
                # 2. Contact (Emails extraction)
                page_text = detail_soup.get_text(" ", strip=True)
                if external_soup:
                    page_text += " " + external_soup.get_text(" ", strip=True)
                
                emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', page_text)
                if emails:
                    # Deduplicate and join
                    unique_emails = sorted(list(set(emails)))
                    email_contact = ", ".join(unique_emails)

                # 3. Dates Extraction (Improved)
                # Look for specific patterns indicating a deadline in the detail page
                deadline_patterns = [
                    r'(?:date|limite|dépôt|avant|jusqu\'au|au)\s*[:\s]\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})', # Explicit deadline
                    r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})' # Any date
                ]
                
                for pattern in deadline_patterns:
                    matches = re.findall(pattern, page_text, re.IGNORECASE)
                    if matches:
                        # Try to parse dates found
                        valid_dates = []
                        for date_str in matches:
                            try:
                                clean_date = date_str.replace('-', '/')
                                dt = datetime.strptime(clean_date, '%d/%m/%Y')
                                if dt.year >= 2023: # Filter out old dates or birthdates
                                    valid_dates.append(dt)
                            except ValueError:
                                continue
                        
                        if valid_dates:
                            # Heuristic: The deadline is often the last date mentioned or the one furthest in the future
                            # But for "deadline" context, usually the specific match is good.
                            # If we matched the specific pattern, take the first valid one.
                            # If we matched generic dates, take the last one (often "signé le X" is start, "avant le Y" is end)
                            selected_date = valid_dates[-1] 
                            date_limite = selected_date.strftime('%Y-%m-%d')
                            break # Stop if we found a date with a pattern
                    
                # 4. Look for linked PDFs in the page
                pdf_link = detail_soup.find('a', href=re.compile(r'\.pdf$', re.I))
                if not pdf_link and external_soup:
                    # Check external page for PDF if not found in main
                    pdf_link = external_soup.find('a', href=re.compile(r'\.pdf$', re.I))
                    if pdf_link:
                         url_source = external_url # Adjust context for relative links

                if pdf_link:
                    pdf_href = pdf_link.get('href')
                    pdf_url = urljoin(url_source, pdf_href)
                    self.logger.info(f"Found PDF in page: {pdf_url}")
                    try:
                        pdf_resp = self.session.get(pdf_url, timeout=30)
                        pdf_resp.raise_for_status()
                        pdf_text = self.pdf_extractor.extract(pdf_resp.content, filename=pdf_url.split('/')[-1])
                        pdf_filename = pdf_url.split('/')[-1]
                    except Exception as e:
                        self.logger.warning(f"Failed to extract PDF {pdf_url}: {e}")

        except Exception as e:
            self.logger.warning(f"Could not fetch details for {url_source}: {e}")

        # Fallback description from list if detail fetch failed or returned nothing
        if not resume:
            desc_elem = container.find(['p', 'div'], class_=re.compile(r'(desc|intro|chapo)', re.I))
            resume = desc_elem.get_text(strip=True) if desc_elem else None
        
        # Fallback Dates extraction (from list item)
        if not date_limite:
            text_content = container.get_text(' ')
            dates = re.findall(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', text_content)
            if dates:
                try:
                    # Take the last date found as potential deadline
                    date_str = dates[-1].replace('-', '/')
                    date_limite = datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                except:
                    pass
        
        # Prepare enrichment text
        enrich_txt_html = f"TITRE: {titre}\n\nRESUME: {resume or ''}\n\nDESCRIPTION: {description}"

        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            date_limite=date_limite,
            organisme='Préfecture de Seine-Saint-Denis',
            resume=resume,
            email_contact=email_contact,
            perimetre_geo='Seine-Saint-Denis (93)',
            enrich_txt_html=enrich_txt_html,
            enrich_txt_pdf=pdf_text,
            pdf_filename=pdf_filename
        )


def main():
    """Test the connector."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    connector = SSDConnector()
    aaps = connector.run()
    
    print(f"\nFound {len(aaps)} AAPs")
    
    # Use standardized saver
    save_raw_dataset(aaps, "ssd")

if __name__ == "__main__":
    main()
