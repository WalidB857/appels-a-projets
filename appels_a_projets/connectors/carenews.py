"""
Carenews connector - HTML scraping.
Source: https://www.carenews.com/appels_a_projets

Carenews is an aggregator of AAPs for associations and ESS actors.
This connector scrapes the listing page and optionally detail pages.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawAAP, save_raw_dataset


@dataclass
class CarenewsConfig:
    """Configuration for Carenews scraper."""
    base_url: str = "https://www.carenews.com"
    listing_url: str = "https://www.carenews.com/appels_a_projets"
    max_pages: int = 5  # Limit pages to scrape (43 pages total)
    fetch_details: bool = True  # Changed to True by default for enrichment
    timeout: int = 30
    user_agent: str = "AAP-Watch/1.0 (contact@example.com)"


class CarenewsConnector(BaseConnector):
    """
    Connector for Carenews AAP listings.
    
    HTML Structure (listing page):
    - Each AAP is in a div with class "job-thumbnail"
    - Title: h3.job-thumbnail__title > a
    - Resume: div.job-thumbnail__text
    - Published date: div.job-thumbnail__date-start
    - Deadline: div.job-thumbnail__date-end
    - Organization: div.job-thumbnail__company > a (optional)
    """
    
    source_id = "carenews"
    source_name = "Carenews"
    
    def __init__(self, config: CarenewsConfig | None = None):
        super().__init__()
        self.config = config or CarenewsConfig()
        self.base_url = self.config.base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        })
    
    def fetch_raw(self) -> list[BeautifulSoup]:
        """
        Fetch listing pages from Carenews.
        Returns a list of BeautifulSoup objects (one per page).
        """
        pages = []
        
        for page_num in range(1, self.config.max_pages + 1):
            url = self.config.listing_url if page_num == 1 else f"{self.config.listing_url}/{page_num}/"
            
            self.logger.info(f"Fetching page {page_num}: {url}")
            
            try:
                response = self.session.get(url, timeout=self.config.timeout)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                pages.append(soup)
                
                # Check if there are more pages
                if not self._has_more_pages(soup, page_num):
                    self.logger.info(f"No more pages after page {page_num}")
                    break
                    
            except requests.RequestException as e:
                self.logger.warning(f"Failed to fetch page {page_num}: {e}")
                break
        
        return pages
    
    def _has_more_pages(self, soup: BeautifulSoup, current_page: int) -> bool:
        """Check if there are more pages to fetch."""
        pagination = soup.select("a[href*='/appels_a_projets/']")
        max_page = current_page
        
        for link in pagination:
            href = link.get("href", "")
            match = re.search(r"/appels_a_projets/(\d+)", href)
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)
        
        return current_page < max_page
    
    def parse(self, pages: list[BeautifulSoup]) -> list[RawAAP]:
        """
        Parse listing pages into RawAAP objects.
        """
        aaps = []
        seen_urls = set()  # Deduplicate within same scrape
        
        for soup in pages:
            # Find all AAP cards - they use "job-thumbnail" class
            cards = soup.select("h3.job-thumbnail__title")
            
            for card in cards:
                try:
                    aap = self._parse_card(card)
                    if aap and aap.url_source not in seen_urls:
                        # Fetch details if configured
                        if self.config.fetch_details:
                            self._enrich_with_details(aap)
                        
                        aaps.append(aap)
                        seen_urls.add(aap.url_source)
                except Exception as e:
                    self.logger.warning(f"Failed to parse card: {e}")
                    continue
        
        return aaps
    
    def _enrich_with_details(self, aap: RawAAP):
        """Fetch detail page and update AAP object."""
        try:
            details = self.fetch_detail(aap.url_source)
            
            if details.get("description"):
                aap.description = details["description"]
                # Populate enrich_txt_html for LLM
                aap.enrich_txt_html = f"TITRE: {aap.titre}\n\nRESUME: {aap.resume or ''}\n\nDESCRIPTION: {aap.description}"
            
            if details.get("email_contact"):
                aap.email_contact = details["email_contact"]
                
            if details.get("url_candidature"):
                aap.url_candidature = details["url_candidature"]
                
        except Exception as e:
            self.logger.warning(f"Failed to enrich {aap.url_source}: {e}")

    def _parse_card(self, title_element) -> RawAAP | None:
        """
        Parse a single AAP card from the listing page.
        
        Args:
            title_element: The h3.job-thumbnail__title element
        """
        # Navigate to parent container
        container = title_element.find_parent("div", class_="job-thumbnail")
        if not container:
            # Try going up further
            container = title_element.find_parent("div", class_="col-lg-6")
        
        if not container:
            container = title_element.parent
        
        # Extract title and URL
        link = title_element.find("a")
        if not link:
            return None
        
        titre_raw = link.get_text(strip=True)
        # Clean title: remove trailing " - " and organization name if present
        titre = self._clean_title(titre_raw)
        
        href = link.get("href", "")
        url_source = href if href.startswith("http") else f"{self.base_url}{href}"
        
        # Extract resume
        resume_elem = container.select_one("div.job-thumbnail__text")
        resume = resume_elem.get_text(strip=True) if resume_elem else None
        if resume:
            # Truncate to 500 chars for raw storage
            resume = resume[:500] + "..." if len(resume) > 500 else resume
        
        # Extract dates
        date_pub_elem = container.select_one("div.job-thumbnail__date-start")
        date_limite_elem = container.select_one("div.job-thumbnail__date-end")
        
        date_publication = self._extract_date(date_pub_elem)
        date_limite = self._extract_date(date_limite_elem)
        
        # Extract organization
        org_elem = container.select_one("div.job-thumbnail__company a")
        organisme = None
        organisme_url = None
        
        if org_elem:
            organisme = org_elem.get_text(strip=True)
            org_href = org_elem.get("href", "")
            organisme_url = org_href if org_href.startswith("http") else f"{self.base_url}{org_href}"
        else:
            # Try to extract from title (format: "Title - Organization")
            organisme = self._extract_org_from_title(titre_raw)
        
        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            date_publication=date_publication,
            date_limite=date_limite,
            organisme=organisme,
            organisme_url=organisme_url,
            resume=resume,
        )
    
    def _clean_title(self, titre_raw: str) -> str:
        """Clean the title by removing trailing ' - ' and organization name."""
        # Remove trailing " - " (with possible trailing spaces)
        titre = re.sub(r'\s*-\s*$', '', titre_raw).strip()
        return titre
    
    def _extract_org_from_title(self, titre_raw: str) -> str | None:
        """Extract organization name from title if format is 'Title - Org - '."""
        # Some titles have format "Title - Organization"
        # But we should only extract if there's a clear separator with org after
        # Don't use this for now - rely on the HTML structure
        return None
    
    def _extract_date(self, element) -> str | None:
        """
        Extract date from element text.
        Expected format: "Publié le : DD.MM.YYYY" or "Date de clôture : DD.MM.YYYY"
        Returns: ISO format string (YYYY-MM-DD) or None
        """
        if not element:
            return None
        
        text = element.get_text(strip=True)
        
        # Find date pattern DD.MM.YYYY
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month}-{day}"
        
        return None
    
    def fetch_detail(self, url: str) -> dict[str, Any]:
        """
        Fetch and parse a detail page for additional information.
        
        Returns additional fields:
        - description (full text)
        - email_contact
        - url_candidature
        - eligibility criteria
        - etc.
        """
        try:
            response = self.session.get(url, timeout=self.config.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            details = {}
            
            # Extract full description
            description_elem = soup.select_one("div.field--name-body")
            if description_elem:
                details["description"] = description_elem.get_text(separator="\n", strip=True)
            
            # Extract contact email
            email_link = soup.select_one("a[href^='mailto:']")
            if email_link:
                details["email_contact"] = email_link.get("href", "").replace("mailto:", "")
            
            # Extract candidature link (often in "RÉPONDRE" button)
            repondre_link = soup.select_one("a.btn-repondre, a[href*='candidat'], a:contains('RÉPONDRE')")
            if repondre_link:
                href = repondre_link.get("href", "")
                if not href.startswith("mailto:"):
                    details["url_candidature"] = href if href.startswith("http") else f"{self.base_url}{href}"
            
            return details
            
        except requests.RequestException as e:
            self.logger.warning(f"Failed to fetch detail page {url}: {e}")
            return {}


def main():
    """Test the connector."""
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    config = CarenewsConfig(max_pages=2, fetch_details=True)
    connector = CarenewsConnector(config)
    
    aaps = connector.run()
    
    print(f"\n{'='*60}")
    print(f"Found {len(aaps)} AAPs")
    print(f"{'='*60}\n")
    
    # Use standardized saver
    save_raw_dataset(aaps, "carenews")


if __name__ == "__main__":
    main()
