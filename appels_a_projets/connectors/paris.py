"""
Paris.fr connector - HTML scraping.
Source: https://www.paris.fr/pages/repondre-a-un-appel-a-projets-5412

Scrapes the "Appels à projets" page from the City of Paris website.
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawAAP


@dataclass
class ParisConfig:
    """Configuration for Paris scraper."""
    base_url: str = "https://www.paris.fr/pages/repondre-a-un-appel-a-projets-5412"
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
        
        # Paris.fr structure often changes, but usually lists are in specific blocks
        # We look for blocks that look like AAP items
        
        # Common selectors for Paris.fr lists
        content_area = soup.find('main') or soup.find('div', class_='content')
        if not content_area:
            self.logger.warning("Could not find main content area")
            return []

        # Look for links that might be AAPs
        # Often in a list or cards
        links = content_area.find_all('a', href=True)
        
        seen_urls = set()
        
        for link in links:
            href = link.get('href', '')
            
            # Filter relevant links (heuristic)
            if not self._is_relevant_link(href, link.get_text()):
                continue
                
            url_source = urljoin("https://www.paris.fr", href)
            
            if url_source in seen_urls:
                continue
                
            try:
                aap = self._parse_item(link, url_source)
                if aap:
                    aaps.append(aap)
                    seen_urls.add(url_source)
            except Exception as e:
                self.logger.warning(f"Error parsing item {url_source}: {e}")
                continue
                
        return aaps

    def _is_relevant_link(self, href: str, text: str) -> bool:
        """Check if a link is likely an AAP."""
        href_lower = href.lower()
        text_lower = text.lower()
        
        # Keywords to include
        keywords = ['appel', 'projet', 'candidature', 'subvention', 'aide']
        if not any(k in href_lower or k in text_lower for k in keywords):
            return False
            
        # Exclude common navigation links
        excludes = ['facebook', 'twitter', 'linkedin', 'instagram', 'contact', 'plan', 'mentions', 'accessibilité']
        if any(e in href_lower for e in excludes):
            return False
            
        return True

    def _parse_item(self, link_elem, url_source) -> RawAAP | None:
        titre = link_elem.get_text(strip=True)
        if not titre or len(titre) < 10: # Skip short links
            return None
            
        # Try to find context (description, date) near the link
        # This is highly dependent on the specific page layout
        container = link_elem.find_parent(['li', 'div', 'article'])
        
        resume = None
        date_limite = None
        
        if container:
            text_content = container.get_text(" ", strip=True)
            
            # Simple resume extraction
            if len(text_content) > len(titre):
                resume = text_content.replace(titre, "").strip()[:500]
            
            # Date extraction
            dates = re.findall(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', text_content)
            if dates:
                try:
                    date_str = dates[-1].replace('-', '/')
                    date_limite = datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                except:
                    pass

        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            date_limite=date_limite,
            organisme='Ville de Paris',
            resume=resume,
            perimetre_geo='Paris (75)'
        )


def main():
    """Test the connector."""
    import json
    import os
    logging.basicConfig(level=logging.INFO)
    
    connector = ParisConnector()
    try:
        aaps = connector.run()
        print(f"\nFound {len(aaps)} AAPs")
        
        # Export for verification
        output = [
            {
                "titre": aap.titre,
                "url_source": aap.url_source,
                "date_limite": aap.date_limite,
                "organisme": aap.organisme,
                "resume": aap.resume,
                "perimetre_geo": aap.perimetre_geo
            }
            for aap in aaps
        ]
        
        os.makedirs("data", exist_ok=True)
        with open("data/paris_raw.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"Exported to data/paris_raw.json")
    except Exception as e:
        print(f"Failed to run connector: {e}")

if __name__ == "__main__":
    main()
