"""
Profession Banlieue connector - RSS feed parser + HTML scraping.
Sources:
- RSS: https://www.professionbanlieue.org/spip.php?page=backend&lang=fr
- HTML: https://www.professionbanlieue.org/Appels-a-projets-Appel-a-manifestation-d-interet

Centre de ressources pour les acteurs de la politique de la ville.
Combine RSS feed + HTML scraping to get all AAPs.

Structure HTML : <a class="lien_article mod"> avec :
- <span class="titre"> : titre de l'AAP
- <span class="introduction"> : description
- <div class="date"> : date de publication
- <div class="date2"> : date limite
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape

import feedparser
import requests
from bs4 import BeautifulSoup

from .base import BaseConnector, RawAAP, save_raw_dataset

logger = logging.getLogger(__name__)


@dataclass
class ProfessionBanlieueConfig:
    """Configuration for Profession Banlieue connector."""
    rss_url: str = "https://www.professionbanlieue.org/spip.php?page=backend&lang=fr"
    html_url: str = "https://www.professionbanlieue.org/Appels-a-projets-Appel-a-manifestation-d-interet"
    timeout: int = 30
    max_items: int = 100


class ProfessionBanlieueConnector(BaseConnector):
    """
    Connector for Profession Banlieue.
    
    Strategy:
    1. Fetch RSS feed (most complete content)
    2. Scrape HTML page (may have additional AAPs not in RSS)
    3. Deduplicate by URL (prioritize RSS data over HTML)
    """
    
    source_id = "professionbanlieue"
    source_name = "Profession Banlieue"
    
    def __init__(self, config: ProfessionBanlieueConfig | None = None):
        super().__init__()
        self.config = config or ProfessionBanlieueConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
    
    def fetch_raw(self) -> dict:
        """
        Fetch both RSS feed and HTML page.
        """
        self.logger.info(f"Fetching from {self.source_name} (RSS + HTML)")
        
        # 1. Fetch RSS
        rss_feed = self._fetch_rss()
        
        # 2. Fetch HTML
        html_soup = self._fetch_html()
        
        return {
            'rss': rss_feed,
            'html': html_soup
        }
    
    def _fetch_rss(self) -> feedparser.FeedParserDict:
        """Fetch RSS feed."""
        self.logger.info(f"Fetching RSS feed from {self.config.rss_url}")
        
        try:
            feed = feedparser.parse(self.config.rss_url)
            
            if feed.bozo:
                self.logger.warning(f"Feed has parsing issues: {feed.bozo_exception}")
            
            self.logger.info(f"Found {len(feed.entries)} items in RSS feed")
            return feed
            
        except Exception as e:
            self.logger.error(f"Failed to fetch RSS feed: {e}")
            # Return empty feed instead of crashing
            return feedparser.FeedParserDict({'entries': []})
    
    def _fetch_html(self) -> BeautifulSoup | None:
        """Fetch and parse HTML page."""
        self.logger.info(f"Fetching HTML page from {self.config.html_url}")
        
        try:
            response = self.session.get(self.config.html_url, timeout=self.config.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            self.logger.info(f"HTML page fetched successfully ({len(response.content):,} bytes)")
            return soup
            
        except Exception as e:
            self.logger.error(f"Failed to fetch HTML page: {e}")
            return None
    
    def parse(self, raw_data: dict) -> list[RawAAP]:
        """
        Parse RSS + HTML into RawAAP objects with deduplication.
        Deduplication strategy: Use URL as key, prioritize RSS data (more complete).
        """
        aaps_by_url = {}  # Deduplicate by URL
        
        # 1. Parse RSS entries (most complete data, higher priority)
        rss_feed = raw_data.get('rss')
        if rss_feed and rss_feed.entries:
            entries = rss_feed.entries[:self.config.max_items]
            
            for entry in entries:
                try:
                    aap = self._parse_rss_entry(entry)
                    if aap:
                        aaps_by_url[aap.url_source] = aap
                except Exception as e:
                    title = entry.get('title', 'unknown')
                    self.logger.warning(f"Failed to parse RSS entry '{title[:50]}': {e}")
        
        self.logger.info(f"Parsed {len(aaps_by_url)} AAPs from RSS")
        
        # 2. Parse HTML page (may have additional AAPs not yet in RSS)
        html_soup = raw_data.get('html')
        if html_soup:
            html_aaps = self._parse_html_page(html_soup)
            
            # Add only new AAPs not already in RSS
            new_count = 0
            for aap in html_aaps:
                if aap.url_source not in aaps_by_url:
                    aaps_by_url[aap.url_source] = aap
                    new_count += 1
                else:
                    self.logger.debug(f"Duplicate AAP (already in RSS): {aap.titre[:50]}")
            
            self.logger.info(f"Found {new_count} additional AAPs from HTML (total: {len(aaps_by_url)})")
        
        aaps = list(aaps_by_url.values())
        self.logger.info(f"✅ Total: {len(aaps)} unique AAPs from {self.source_name}")
        
        # Save using standardized format
        save_raw_dataset(aaps, self.source_id)
        
        return aaps
    
    def _parse_rss_entry(self, entry: dict) -> RawAAP | None:
        """
        Parse a single RSS entry into a RawAAP object.
        """
        # Required: title
        titre = entry.get('title')
        if not titre:
            return None
        
        titre = self._clean_html(titre)
        
        # Required: link
        url_source = entry.get('link')
        if not url_source:
            return None
        
        # Description (HTML content)
        # Priority: content > summary > description
        description = ""
        full_content = ""
        
        # 1. Try content:encoded (most complete)
        if 'content' in entry and entry.content:
            # feedparser stores content as list of dicts with 'value' key
            if isinstance(entry.content, list) and len(entry.content) > 0:
                full_content = entry.content[0].get('value', '')
        
        # 2. Fallback to summary or description (shorter version)
        if 'summary' in entry:
            description = entry.summary
        elif 'description' in entry:
            description = entry.description
        
        # Use full content if available, otherwise use description
        text_for_llm = full_content if full_content else description
        description_clean = self._clean_html(text_for_llm)
        
        # === FILTRAGE AAP ===
        # Exclure les offres d'emploi (contiennent "MISSIONS" dans description)
        if re.search(r'<p>\s*MISSIONS?\s*', description, re.IGNORECASE):
            self.logger.debug(f"Skipping job offer: {titre[:50]}")
            return None
        
        # Vérifier si c'est bien un AAP (mot-clé requis dans titre ou contenu)
        if not self._is_aap(titre, description_clean):
            self.logger.debug(f"Skipping non-AAP entry: {titre[:50]}")
            return None
        
        # Publication date
        date_publication = None
        if 'published_parsed' in entry and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6])
                date_publication = dt.strftime("%Y-%m-%d")
            except:
                pass
        
        # Categories → tags
        tags = []
        if 'tags' in entry:
            tags = [self._clean_html(tag.term) for tag in entry.tags if hasattr(tag, 'term')]
        
        # Organization (always same for this source)
        organisme = "Profession Banlieue"
        
        # Geographic scope (politique de la ville → often IDF but can be national)
        perimetre_geo = "National"  # Default, LLM can refine
        
        # Extract emails from description
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', description_clean)
        email_contact = emails[0] if emails else None
        
        # Extract deadline from content (common patterns)
        date_limite = self._extract_deadline(text_for_llm)
        
        # Enrichment text for LLM (use full content if available)
        enrich_txt_html = f"TITRE: {titre}\nURL: {url_source}\n\n{description_clean}"
        
        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            description=description_clean,
            organisme=organisme,
            date_publication=date_publication,
            date_limite=date_limite,
            tags=tags,
            perimetre_geo=perimetre_geo,
            email_contact=email_contact,
            enrich_txt_html=enrich_txt_html,
        )
    
    def _parse_html_page(self, soup: BeautifulSoup) -> list[RawAAP]:
        """
        Parse HTML page to extract AAPs.
        
        Structure SPIP : <a class="lien_article mod"> avec :
        - <span class="titre"> : titre de l'AAP
        - <span class="introduction"> : description
        - <div class="date"> : date de publication
        - <div class="date2"> : date limite
        """
        aaps = []
        
        # Chercher tous les liens d'articles AAP
        aap_links = soup.find_all('a', class_='lien_article')
        
        # Filtrer ceux avec la classe 'mod'
        aap_mod_links = [link for link in aap_links if 'mod' in link.get('class', [])]
        
        self.logger.info(f"Found {len(aap_mod_links)} AAP links in HTML page")
        
        for link in aap_mod_links:
            try:
                aap = self._parse_html_item(link)
                if aap:
                    aaps.append(aap)
            except Exception as e:
                self.logger.warning(f"Failed to parse HTML item: {e}")
        
        return aaps
    
    def _parse_html_item(self, link) -> RawAAP | None:
        """
        Parse a single HTML <a class='lien_article mod'> element.
        """
        # URL
        url_source = link.get('href', '')
        if not url_source:
            return None
        
        # Make URL absolute
        if not url_source.startswith('http'):
            url_source = f"https://www.professionbanlieue.org/{url_source.lstrip('/')}"
        
        # Titre : <span class="titre">
        titre_span = link.find('span', class_='titre')
        if not titre_span:
            return None
        
        titre = self._clean_html(titre_span.get_text())
        
        # Description : <span class="introduction">
        intro_span = link.find('span', class_='introduction')
        description_clean = self._clean_html(intro_span.get_text()) if intro_span else ""
        
        # Date publication : <div class="date">
        date_div = link.find('div', class_='date')
        date_publication = self._parse_date_div(date_div) if date_div else None
        
        # Date limite : <div class="date2">
        date2_div = link.find('div', class_='date2')
        date_limite = self._parse_date_div(date2_div) if date2_div else None
        
        # === FILTRAGE AAP ===
        # Exclure les offres d'emploi
        if self._is_job_offer(str(link), titre, description_clean):
            self.logger.debug(f"Skipping job offer: {titre[:50]}")
            return None
        
        # Vérifier si c'est bien un AAP
        if not self._is_aap(titre, description_clean):
            self.logger.debug(f"Skipping non-AAP item: {titre[:50]}")
            return None
        
        # Extract email
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', description_clean)
        email_contact = emails[0] if emails else None
        
        organisme = "Profession Banlieue"
        perimetre_geo = "National"
        
        enrich_txt_html = f"TITRE: {titre}\nURL: {url_source}\n\n{description_clean}"
        
        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            description=description_clean,
            organisme=organisme,
            date_publication=date_publication,
            date_limite=date_limite,
            tags=[],
            perimetre_geo=perimetre_geo,
            email_contact=email_contact,
            enrich_txt_html=enrich_txt_html,
        )
    
    def _parse_date_div(self, date_div) -> str | None:
        """
        Parse une div de date SPIP.
        
        Format : <div class="date">jeu <span class="date_num">4</span> déc</div>
        Retour : "4 déc" ou "4 décembre" selon disponibilité
        """
        if not date_div:
            return None
        
        try:
            # Extraire le numéro du jour : <span class="date_num">
            date_num_span = date_div.find('span', class_='date_num')
            date_num = date_num_span.get_text(strip=True) if date_num_span else ''
            
            # Extraire le mois (dernier texte dans la div)
            # Les contents incluent : jour_nom, <span>, mois
            text_nodes = [str(node).strip() for node in date_div.contents if isinstance(node, str)]
            month = text_nodes[-1] if text_nodes else ''
            
            if date_num and month:
                date_str = f"{date_num} {month}"
                # Tenter de parser vers format complet
                return self._parse_french_date(date_str)
            
        except Exception as e:
            self.logger.warning(f"Failed to parse date div: {e}")
        
        return None
    
    def _is_job_offer(self, html: str, titre: str, description: str) -> bool:
        """Check if item is a job offer (to exclude)."""
        # Vérifier MISSIONS dans HTML
        if re.search(r'<p>\s*MISSIONS?\s*', html, re.IGNORECASE):
            return True
        if re.search(r'MISSIONS?\s*[:<]', html, re.IGNORECASE):
            return True
        if re.search(r'offre\s+d[\'\"]emploi', f"{titre} {description}", re.IGNORECASE):
            return True
        return False
    
    def _is_aap(self, titre: str, description: str) -> bool:
        """Check if content matches AAP keywords."""
        keywords = [
            r"appel\s+[aà]\s+projets?",
            r"appel\s+[aà]\s+candidatures?",
            r"appel\s+[aà]\s+manifestation\s+d[' ]int[eé]r[eê]t",
            r"\bami\b",
            r"\baap\b",
            r"\bfipd\b",
            r"\bfdva\b",
            r"d[eé]p[oô]t\s+de\s+candidature",
            r"dossier\s+de\s+candidature",
            r"date\s+limite",
            r"date\s+de\s+cl[oô]ture",
            r"candidatures?",
            r"calendrier\s+de\s+l[' ]appel",
            r"s[eé]lection\s+des\s+projets",
            r"porteurs?\s+de\s+projets?",
            r"crit[eè]res?\s+de\s+s[eé]lection",
            r"conditions?\s+d[' ][eé]ligibilit[eé]",
            r"subvention",
            r"aide\s+financi[eè]re",
            r"montant\s+de\s+l[' ]aide",
            r"laur[eé]ats?",
            r"projets?\s+retenus?",
        ]
        
        combined_text = f"{titre} {description}".lower()
        return any(re.search(pattern, combined_text, re.IGNORECASE) for pattern in keywords)
    
    def _extract_deadline(self, text: str) -> str | None:
        """Extract deadline date from text."""
        deadline_patterns = [
            r'date limite.*?(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})',
            r'avant le\s+(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})',
            r"jusqu'au\s+(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4})",
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',  # Format DD/MM/YYYY or DD-MM-YYYY
        ]
        
        for pattern in deadline_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                date_limite = self._parse_french_date(date_str)
                if date_limite:
                    return date_limite
        
        return None
    
    def _parse_french_date(self, date_str: str) -> str | None:
        """
        Parse French date format to YYYY-MM-DD.
        Formats: 
        - DD/MM/YYYY, DD-MM-YYYY
        - "27 février 2026" or "27 fév 2026"
        - "4 déc" (sans année → assume année courante)
        """
        if not date_str:
            return None
        
        # French month names mapping (full + abbreviations)
        french_months = {
            'janvier': 1, 'jan': 1, 'janv': 1,
            'février': 2, 'fév': 2, 'fevrier': 2,
            'mars': 3, 'mar': 3,
            'avril': 4, 'avr': 4,
            'mai': 5,
            'juin': 6,
            'juillet': 7, 'juil': 7,
            'août': 8, 'aout': 8,
            'septembre': 9, 'sep': 9, 'sept': 9,
            'octobre': 10, 'oct': 10,
            'novembre': 11, 'nov': 11,
            'décembre': 12, 'déc': 12, 'dec': 12, 'decembre': 12
        }
        
        try:
            # Try format "27 février 2026" or "4 déc"
            parts = date_str.lower().split()
            if len(parts) >= 2:
                day = int(parts[0])
                month_name = parts[1].strip('.')
                month = french_months.get(month_name)
                
                if month:
                    # Année fournie ou année courante
                    year = int(parts[2]) if len(parts) >= 3 else datetime.now().year
                    dt = datetime(year, month, day)
                    return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError) as e:
            self.logger.debug(f"Could not parse French date format '{date_str}': {e}")
        
        try:
            # Try DD/MM/YYYY or DD-MM-YYYY
            parts = re.split(r'[/-]', date_str)
            if len(parts) == 3:
                day, month, year = parts
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
        
        return None
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        if not text:
            return ""
        
        # Decode HTML entities
        text = unescape(text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text


def main():
    """Test the connector."""
    logging.basicConfig(level=logging.INFO)
    
    connector = ProfessionBanlieueConnector()
    
    print("🔍 Fetching Profession Banlieue (RSS + HTML)...")
    aaps = connector.run()
    
    print(f"\n{'='*60}")
    print(f"Found {len(aaps)} unique AAPs")
    print(f"{'='*60}\n")
    
    for aap in aaps[:5]:
        print(f"- {aap.titre}")
        print(f"  📅 {aap.date_publication or 'Date inconnue'}")
        print(f"  🔗 {aap.url_source}\n")


if __name__ == "__main__":
    main()
