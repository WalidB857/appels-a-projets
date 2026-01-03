"""
Processing module for AAP data.
"""

from .normalizer import normalize_all, raw_to_aap

__all__ = [
    "raw_to_aap",
    "normalize_all",
]
