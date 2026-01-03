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
