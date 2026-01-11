"""
Île-de-France OpenData connector - REST API.
Source: https://data.iledefrance.fr/explore/dataset/aides-appels-a-projets/api/

This connector fetches AAPs from the Région Île-de-France open data platform.
The API provides well-structured data with rich metadata.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any

import requests

from .base import BaseConnector, RawAAP, save_raw_dataset


@dataclass
class IleDeFranceConfig:
    """Configuration for IDF OpenData API."""
    api_url: str = "https://data.iledefrance.fr/api/records/1.0/search/"
    dataset: str = "aides-appels-a-projets"
    rows_per_page: int = 100  # Max rows per request
    max_records: int = 500  # Max total records to fetch
    timeout: int = 30


class IleDeFranceConnector(BaseConnector):
    """
    Connector for Île-de-France OpenData AAP API.
    
    API Response Structure:
    - records[].fields contains the AAP data
    - records[].recordid is the unique identifier
    - records[].record_timestamp is the last update time
    
    Key fields mapping:
    - nom_de_l_aide_de_la_demarche → titre
    - porteur_aide → organisme
    - date_ouverture → date_publication
    - date_cloture → date_limite
    - chapo_txt / objectif_txt → resume
    - url_descriptif → url_source
    - theme → categories
    - qui_peut_en_beneficier → public_cible
    - mots_cles → tags
    """
    
    source_id = "iledefrance_opendata"
    source_name = "Île-de-France OpenData"
    
    def __init__(self, config: IleDeFranceConfig | None = None):
        super().__init__()
        self.config = config or IleDeFranceConfig()
        self.base_url = self.config.api_url
        self.session = requests.Session()
    
    def fetch_raw(self) -> list[dict]:
        """
        Fetch all records from the API with pagination.
        Returns a list of raw record dictionaries.
        """
        all_records = []
        start = 0
        
        while start < self.config.max_records:
            params = {
                "dataset": self.config.dataset,
                "rows": self.config.rows_per_page,
                "start": start,
            }
            
            self.logger.info(f"Fetching records {start} to {start + self.config.rows_per_page}")
            
            try:
                response = self.session.get(
                    self.config.api_url,
                    params=params,
                    timeout=self.config.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                records = data.get("records", [])
                if not records:
                    break
                
                all_records.extend(records)
                
                # Check if we've fetched all available records
                nhits = data.get("nhits", 0)
                if start + len(records) >= nhits:
                    break
                
                start += self.config.rows_per_page
                
            except requests.RequestException as e:
                self.logger.error(f"Failed to fetch records: {e}")
                break
        
        self.logger.info(f"Fetched {len(all_records)} total records from API")
        return all_records
    
    def parse(self, records: list[dict]) -> list[RawAAP]:
        """
        Parse API records into RawAAP objects.
        """
        aaps = []
        
        for record in records:
            try:
                aap = self._parse_record(record)
                if aap:
                    aaps.append(aap)
            except Exception as e:
                record_id = record.get("recordid", "unknown")
                self.logger.warning(f"Failed to parse record {record_id}: {e}")
                continue
        
        return aaps
    
    def _parse_record(self, record: dict) -> RawAAP | None:
        """
        Parse a single API record into a RawAAP object.
        """
        fields = record.get("fields", {})
        
        # Required field: title
        titre = fields.get("nom_de_l_aide_de_la_demarche")
        if not titre:
            return None
        
        # URL source
        url_source = fields.get("url_descriptif")
        if not url_source:
            # Build URL from reference if available
            ref = fields.get("reference_administrative")
            if ref:
                url_source = f"https://www.iledefrance.fr/aides-et-appels-a-projets/{ref}"
        
        if not url_source:
            url_source = f"https://data.iledefrance.fr/explore/dataset/aides-appels-a-projets/table/?q={record.get('recordid', '')}"
        
        # Organization
        organisme = fields.get("porteur_aide", "Région Île-de-France")
        
        # Dates
        date_publication = self._parse_date(fields.get("date_ouverture"))
        date_limite = self._parse_date(fields.get("date_cloture"))
        
        if not date_limite:
            date_limite = "2050-01-01"
        
        # Resume: prefer chapo_txt, fallback to objectif_txt
        resume = fields.get("chapo_txt") or fields.get("objectif_txt")
        if resume:
            resume = self._clean_html(resume)
            resume = resume[:500] + "..." if len(resume) > 500 else resume
        
        # Full description
        description = fields.get("objectif_txt")
        if description:
            description = self._clean_html(description)
        
        # Categories from theme
        categories = []
        theme = fields.get("theme")
        if theme:
            categories = self._map_theme_to_categories(theme)
        
        # Tags from mots_cles
        tags = []
        mots_cles = fields.get("mots_cles")
        if mots_cles:
            tags = [t.strip() for t in mots_cles.split(",") if t.strip()]
        
        # Public cible - REMOVED as per instructions to let LLM handle it
        public_cible = []
        
        # Geographic scope (always IDF for this source)
        perimetre_geo = "Île-de-France"
        
        # Contact info
        contact = fields.get("contact")
        email_contact = self._extract_email(contact) if contact else None
        
        # Candidature URL from demarches
        demarches = fields.get("demarches_txt") or fields.get("demarches")
        url_candidature = self._extract_candidature_url(demarches) if demarches else None
        
        # Construct enrichment text from API fields - using raw fields as requested
        # We use the raw fields directly to give full context to the LLM
        enrich_txt_html = f"TITRE: {fields.get('nom_de_l_aide_de_la_demarche', '')}\n\n"
        
        if fields.get("chapo_txt"):
            enrich_txt_html += f"RESUME (chapo): {fields.get('chapo_txt')}\n\n"
            
        if fields.get("objectif_txt"):
            enrich_txt_html += f"OBJECTIF: {fields.get('objectif_txt')}\n\n"
            
        if fields.get("beneficiaires"):
            enrich_txt_html += f"BENEFICIAIRES: {fields.get('beneficiaires')}\n\n"
        
        if fields.get("qui_peut_en_beneficier"):
            enrich_txt_html += f"QUI PEUT EN BENEFICIER: {fields.get('qui_peut_en_beneficier')}\n\n"
            
        if fields.get("conditions"):
            enrich_txt_html += f"CONDITIONS: {fields.get('conditions')}\n\n"
            
        if fields.get("montant"):
            enrich_txt_html += f"MONTANT: {fields.get('montant')}\n\n"
            
        if fields.get("demarches_txt"):
            enrich_txt_html += f"DEMARCHES: {fields.get('demarches_txt')}\n\n"
            
        if fields.get("contact"):
            enrich_txt_html += f"CONTACT: {fields.get('contact')}\n"

        return RawAAP(
            titre=titre,
            url_source=url_source,
            source_id=self.source_id,
            date_publication=date_publication,
            date_limite=date_limite,
            organisme=organisme,
            resume=resume,
            description=description,
            categories=categories,
            tags=tags,
            public_cible=public_cible,
            perimetre_geo=perimetre_geo,
            email_contact=email_contact,
            url_candidature=url_candidature,
            enrich_txt_html=enrich_txt_html, # Added for LLM processing
        )
    
    def _parse_date(self, date_str: str | None) -> str | None:
        """
        Parse ISO date string to YYYY-MM-DD format.
        Input format: 2023-09-04T22:00:00+00:00
        """
        if not date_str:
            return None
        
        try:
            # Handle ISO format
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return None
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        # Decode HTML entities
        text = unescape(text)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _map_theme_to_categories(self, theme: str) -> list[str]:
        """
        Map IDF themes to our standard categories.
        """
        theme_lower = theme.lower()
        
        mapping = {
            "emploi": "insertion-emploi",
            "insertion": "insertion-emploi",
            "formation": "insertion-emploi",
            "éducation": "education-jeunesse",
            "jeunesse": "education-jeunesse",
            "lycée": "education-jeunesse",
            "recherche": "education-jeunesse",
            "santé": "sante-handicap",
            "handicap": "sante-handicap",
            "solidarité": "solidarite-inclusion",
            "social": "solidarite-inclusion",
            "inclusion": "solidarite-inclusion",
            "culture": "culture-sport",
            "sport": "culture-sport",
            "environnement": "environnement-transition",
            "transition": "environnement-transition",
            "écologie": "environnement-transition",
            "numérique": "numerique",
            "digital": "numerique",
            "association": "vie-associative",
        }
        
        categories = []
        for keyword, category in mapping.items():
            if keyword in theme_lower and category not in categories:
                categories.append(category)
        
        if not categories:
            categories.append("autre")
        
        return categories
    
    def _extract_email(self, contact: str) -> str | None:
        """Extract email from contact string."""
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', contact)
        return match.group(0) if match else None
    
    def _extract_candidature_url(self, demarches: str) -> str | None:
        """Extract candidature URL from demarches text."""
        # Look for mesdemarches.iledefrance.fr or other URLs
        urls = re.findall(r'https?://[^\s<>"\']+', demarches)
        for url in urls:
            if "mesdemarches" in url or "candidat" in url:
                return url
        return urls[0] if urls else None


def main():
    """Test the connector."""
    import logging
    
    logging.basicConfig(level=logging.INFO)
    
    config = IleDeFranceConfig(max_records=100)
    connector = IleDeFranceConnector(config)
    
    aaps = connector.run()
    
    print(f"\n{'='*60}")
    print(f"Found {len(aaps)} AAPs")
    print(f"{'='*60}\n")
    
    # Use standardized saver
    save_raw_dataset(aaps, "iledefrance")


if __name__ == "__main__":
    main()
