"""
Connectors package for AAP data sources.
"""

from .airtable_connector import AirtableConnector
from .base import BaseConnector, RawAAP
from .carenews import CarenewsConfig, CarenewsConnector
from .iledefrance_opendata import IleDeFranceConfig, IleDeFranceConnector

__all__ = [
    "BaseConnector",
    "RawAAP",
    "CarenewsConnector",
    "CarenewsConfig",
    "IleDeFranceConnector",
    "IleDeFranceConfig",
    "AirtableConnector",
]
