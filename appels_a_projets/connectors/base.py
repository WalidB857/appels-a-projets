"""
Base connector class for AAP sources.
All connectors should inherit from BaseConnector.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class RawAAP:
    """
    Raw AAP data extracted from a source.
    This is the intermediate format before normalization.
    Fields are optional since different sources provide different data.
    """
    titre: str
    url_source: str
    source_id: str
    
    # Dates
    date_publication: str | None = None
    date_limite: str | None = None
    
    # Organization
    organisme: str | None = None
    organisme_url: str | None = None
    organisme_logo: str | None = None
    
    # Content
    resume: str | None = None
    description: str | None = None
    
    # Contact
    url_candidature: str | None = None
    email_contact: str | None = None
    
    # Classification (to be enriched later, possibly by LLM)
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    # Geographic scope
    perimetre_geo: str | None = None
    
    # Target audience
    public_cible: list[str] = field(default_factory=list)
    
    # Financial info
    montant_min: float | None = None
    montant_max: float | None = None
    
    # Metadata
    raw_html: str | None = None
    scraped_at: datetime = field(default_factory=datetime.now)
    
    # Enrichment
    enrich_txt_html: str | None = None
    enrich_txt_pdf: str | None = None
    pdf_filename: str | None = None


def save_raw_dataset(aaps: list[RawAAP], source_name: str, output_dir: str = "data"):
    """
    Standardized method to save raw dataset for any connector.
    
    Creates:
    - {output_dir}/{source_name}/metadata.json
    - {output_dir}/{source_name}/content/{id}.txt
    """
    import json
    import hashlib
    import os
    from pathlib import Path
    
    # Setup directories
    base_dir = Path(output_dir) / source_name
    content_dir = base_dir / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    
    clean_metadata = []
    
    for aap in aaps:
        # 1. Create unique ID (hash of URL)
        doc_id = hashlib.md5(aap.url_source.encode()).hexdigest()
        
        # 2. Prepare full text for LLM
        full_text = f"TITRE: {aap.titre}\n"
        full_text += f"URL: {aap.url_source}\n"
        if aap.date_limite:
            full_text += f"DATE_LIMITE: {aap.date_limite}\n"
        full_text += "\n"
        
        if aap.enrich_txt_html:
            full_text += f"--- SOURCE HTML ---\n{aap.enrich_txt_html}\n\n"
        
        if aap.enrich_txt_pdf:
            full_text += f"--- CONTENU PDF ({aap.pdf_filename or 'doc'}) ---\n{aap.enrich_txt_pdf}"
        
        # 3. Save text to file
        txt_filename = f"{doc_id}.txt"
        content_file_path = content_dir / txt_filename
        with open(content_file_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        
        # 4. Prepare metadata for JSON
        # Convert RawAAP to dict, excluding heavy text fields
        meta = {
            "id": doc_id,
            "titre": aap.titre,
            "url_source": aap.url_source,
            "source_id": aap.source_id,
            "date_limite": aap.date_limite,
            "date_publication": aap.date_publication,
            "organisme": aap.organisme,
            "resume": aap.resume,
            "perimetre_geo": aap.perimetre_geo,
            "pdf_filename": aap.pdf_filename,
            "content_file": str(content_file_path),
            # Keep existing enrichment if any
            "categories": aap.categories,
            "tags": aap.tags,
            "public_cible": aap.public_cible,
            "montant_min": aap.montant_min,
            "montant_max": aap.montant_max,
            "url_candidature": aap.url_candidature,
            "email_contact": aap.email_contact
        }
        clean_metadata.append(meta)
    
    # 5. Save lightweight JSON
    metadata_path = base_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(clean_metadata, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(aaps)} records to {base_dir}")
    return metadata_path


class BaseConnector(ABC):
    """
    Abstract base class for all AAP connectors.
    
    Each connector must implement:
    - fetch_raw(): Get raw data from the source
    - parse(): Convert raw data to list of RawAAP
    """
    
    source_id: str
    source_name: str
    base_url: str
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    def fetch_raw(self) -> Any:
        """
        Fetch raw data from the source.
        Returns the raw response (HTML, JSON, etc.)
        """
        pass
    
    @abstractmethod
    def parse(self, raw_data: Any) -> list[RawAAP]:
        """
        Parse raw data into a list of RawAAP objects.
        """
        pass
    
    def run(self) -> list[RawAAP]:
        """
        Execute the full pipeline: fetch + parse.
        Handles errors gracefully.
        """
        try:
            self.logger.info(f"Starting {self.source_name} connector...")
            raw_data = self.fetch_raw()
            aaps = self.parse(raw_data)
            self.logger.info(f"Successfully extracted {len(aaps)} AAPs from {self.source_name}")
            return aaps
        except Exception as e:
            self.logger.error(f"Error in {self.source_name} connector: {e}")
            raise
