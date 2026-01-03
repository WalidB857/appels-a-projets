"""
Normalizer - Convert RawAAP to normalized AAP.

This module handles the conversion from connector-specific RawAAP
to the canonical AAP format.
"""

from datetime import date, datetime

from appels_a_projets.connectors.base import RawAAP
from appels_a_projets.models.aap import AAP, Category, Source


def parse_date(date_str: str | None) -> date | None:
    """Parse date string (YYYY-MM-DD) to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def normalize_categories(raw_categories: list[str]) -> list[Category]:
    """Convert raw category strings to Category enum values."""
    if not raw_categories:
        return [Category.AUTRE]
    
    result = []
    for cat in raw_categories:
        try:
            result.append(Category(cat))
        except ValueError:
            # Try to match by substring
            cat_lower = cat.lower()
            matched = False
            for category in Category:
                if category.value in cat_lower or cat_lower in category.value:
                    result.append(category)
                    matched = True
                    break
            if not matched:
                result.append(Category.AUTRE)
    
    return result if result else [Category.AUTRE]


def raw_to_aap(raw: RawAAP, source_name: str, source_url: str) -> AAP:
    """
    Convert a RawAAP to a normalized AAP.
    
    Args:
        raw: RawAAP object from a connector
        source_name: Human-readable name of the source
        source_url: URL of the source listing page
    
    Returns:
        Normalized AAP object
    """
    source = Source(
        id=raw.source_id,
        name=source_name,
        url=source_url,
        fetched_at=raw.scraped_at,
    )
    
    return AAP(
        titre=raw.titre,
        url_source=raw.url_source,
        source=source,
        organisme=raw.organisme or "Inconnu",
        organisme_url=raw.organisme_url,
        date_publication=parse_date(raw.date_publication),
        date_limite=parse_date(raw.date_limite),
        categories=normalize_categories(raw.categories),
        tags=raw.tags,
        perimetre_geo=raw.perimetre_geo,
        public_cible=raw.public_cible,
        montant_min=raw.montant_min,
        montant_max=raw.montant_max,
        resume=raw.resume or "",
        description=raw.description,
        url_candidature=raw.url_candidature,
        email_contact=raw.email_contact,
    )


def normalize_all(
    raw_aaps: list[RawAAP],
    source_name: str,
    source_url: str,
) -> list[AAP]:
    """
    Convert a list of RawAAPs to normalized AAPs.
    
    Args:
        raw_aaps: List of RawAAP objects
        source_name: Human-readable name of the source
        source_url: URL of the source listing page
    
    Returns:
        List of normalized AAP objects
    """
    return [raw_to_aap(raw, source_name, source_url) for raw in raw_aaps]
