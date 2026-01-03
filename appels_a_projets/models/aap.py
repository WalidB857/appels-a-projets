"""
AAP Data Models - Normalized schema for Appels à Projets.

This module defines the Pydantic models for:
- AAP: The normalized AAP schema (output format)
- RawAAP: The intermediate format from connectors (in base.py)

Design decisions:
- Use Pydantic v2 for validation and serialization
- Categories are a fixed taxonomy for filtering
- Tags are free-form for discovery/search
- Fingerprint enables deduplication across sources
"""

from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator


class Category(str, Enum):
    """
    Fixed taxonomy of AAP categories.
    Used for filtering in the UI.
    """
    INSERTION_EMPLOI = "insertion-emploi"
    EDUCATION_JEUNESSE = "education-jeunesse"
    SANTE_HANDICAP = "sante-handicap"
    CULTURE_SPORT = "culture-sport"
    ENVIRONNEMENT_TRANSITION = "environnement-transition"
    SOLIDARITE_INCLUSION = "solidarite-inclusion"
    VIE_ASSOCIATIVE = "vie-associative"
    NUMERIQUE = "numerique"
    AUTRE = "autre"


class PublicCible(str, Enum):
    """
    Target audience types.
    """
    ASSOCIATIONS = "associations"
    ESUS = "esus"  # Entreprises Solidaires d'Utilité Sociale
    COLLECTIFS = "collectifs"
    FONDATIONS = "fondations"
    COLLECTIVITES = "collectivites"
    ETABLISSEMENTS_PUBLICS = "etablissements-publics"
    ENTREPRISES_ESS = "entreprises-ess"
    PARTICULIERS = "particuliers"
    AUTRE = "autre"


class Source(BaseModel):
    """
    Source metadata for an AAP.
    """
    id: str = Field(..., description="Source identifier (e.g., 'carenews', 'iledefrance_opendata')")
    name: str = Field(..., description="Human-readable source name")
    url: str = Field(..., description="URL where the AAP was found")
    fetched_at: datetime = Field(default_factory=datetime.now, description="When the AAP was fetched")


class AAP(BaseModel):
    """
    Normalized AAP (Appel à Projets) schema.
    
    This is the canonical format for all AAPs, regardless of source.
    All connectors should produce data that can be converted to this format.
    """
    
    # Identity
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier (UUID)")
    
    # Core fields (required)
    titre: str = Field(..., min_length=1, max_length=500, description="Title of the AAP")
    url_source: str = Field(..., description="Original URL of the AAP")
    source: Source = Field(..., description="Source metadata")
    
    # Organization
    organisme: str = Field(default="Inconnu", description="Organization offering the AAP")
    organisme_url: str | None = Field(default=None, description="URL of the organization's page")
    
    # Dates
    date_publication: date | None = Field(default=None, description="Publication date")
    date_limite: date | None = Field(default=None, description="Application deadline")
    
    # Classification
    categories: list[Category] = Field(
        default_factory=lambda: [Category.AUTRE],
        description="Fixed taxonomy categories (1-3)"
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Free-form tags for discovery"
    )
    
    # Geographic scope
    perimetre_geo: str | None = Field(
        default=None,
        description="Geographic scope (e.g., 'Paris', 'Île-de-France', 'National')"
    )
    
    # Target audience
    public_cible: list[str] = Field(
        default_factory=list,
        description="Target audience types"
    )
    
    # Financial info
    montant_min: float | None = Field(default=None, ge=0, description="Minimum funding amount in euros")
    montant_max: float | None = Field(default=None, ge=0, description="Maximum funding amount in euros")
    
    # Content
    resume: Annotated[str, Field(max_length=500)] = Field(
        default="",
        description="Short summary (max 500 chars)"
    )
    description: str | None = Field(default=None, description="Full description")
    
    # Contact
    url_candidature: str | None = Field(default=None, description="URL to apply")
    email_contact: str | None = Field(default=None, description="Contact email")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Record creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    
    @computed_field
    @property
    def fingerprint(self) -> str:
        """
        Unique fingerprint for deduplication.
        Based on: titre + organisme + date_limite
        """
        components = [
            self.titre.lower().strip(),
            self.organisme.lower().strip(),
            str(self.date_limite) if self.date_limite else "",
        ]
        content = "|".join(components)
        return sha256(content.encode()).hexdigest()[:16]
    
    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if the AAP is still open for applications."""
        if not self.date_limite:
            return True  # No deadline = assume active
        return self.date_limite >= date.today()
    
    @computed_field
    @property
    def days_remaining(self) -> int | None:
        """Days until deadline, or None if no deadline."""
        if not self.date_limite:
            return None
        delta = self.date_limite - date.today()
        return max(0, delta.days)
    
    @field_validator("categories", mode="before")
    @classmethod
    def validate_categories(cls, v):
        """Ensure categories is a list and convert strings to Category enum."""
        if not v:
            return [Category.AUTRE]
        if isinstance(v, str):
            v = [v]
        result = []
        for cat in v:
            if isinstance(cat, Category):
                result.append(cat)
            elif isinstance(cat, str):
                try:
                    result.append(Category(cat))
                except ValueError:
                    result.append(Category.AUTRE)
        return result if result else [Category.AUTRE]
    
    @field_validator("resume", mode="before")
    @classmethod
    def truncate_resume(cls, v):
        """Truncate resume to max length."""
        if v and len(v) > 500:
            return v[:497] + "..."
        return v or ""
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "titre": "Concours 2026 de La France s'engage",
                "url_source": "https://www.carenews.com/appels-a-projet/concours-2026",
                "source": {
                    "id": "carenews",
                    "name": "Carenews",
                    "url": "https://www.carenews.com/appels_a_projets"
                },
                "organisme": "Fondation La France s'engage",
                "date_publication": "2025-12-24",
                "date_limite": "2026-01-29",
                "categories": ["solidarite-inclusion", "vie-associative"],
                "tags": ["innovation sociale", "ESS", "changement d'échelle"],
                "perimetre_geo": "National",
                "public_cible": ["associations", "fondations", "esus"],
                "montant_max": 300000,
                "resume": "Concours annuel sélectionnant 10-15 projets d'innovation sociale...",
            }
        }
    }


class AAPCollection(BaseModel):
    """
    Collection of AAPs with metadata.
    """
    aaps: list[AAP] = Field(default_factory=list)
    total: int = Field(default=0)
    fetched_at: datetime = Field(default_factory=datetime.now)
    sources: list[str] = Field(default_factory=list)
    
    def __len__(self) -> int:
        return len(self.aaps)
    
    def __iter__(self):
        return iter(self.aaps)
    
    def add(self, aap: AAP) -> bool:
        """
        Add an AAP if not already present (by fingerprint).
        Returns True if added, False if duplicate.
        """
        existing_fingerprints = {a.fingerprint for a in self.aaps}
        if aap.fingerprint in existing_fingerprints:
            return False
        self.aaps.append(aap)
        self.total = len(self.aaps)
        return True
    
    def filter_active(self) -> "AAPCollection":
        """Return only active AAPs."""
        return AAPCollection(
            aaps=[a for a in self.aaps if a.is_active],
            sources=self.sources,
        )
    
    def filter_by_category(self, category: Category) -> "AAPCollection":
        """Return AAPs matching a category."""
        return AAPCollection(
            aaps=[a for a in self.aaps if category in a.categories],
            sources=self.sources,
        )
    
    def to_dataframe(self):
        """Convert to pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame([a.model_dump() for a in self.aaps])
