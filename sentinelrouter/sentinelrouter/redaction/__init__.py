"""
Redaction module for sensitive data protection.

Provides pattern-based detection and masking of:
- Cloud provider credentials (AWS, GCP, Azure)
- PII (SSN, credit cards, etc.)
- Database connection strings
"""

from .engine import RedactionEngine, RedactionMode
from .patterns import CLOUDS_AND_PII_PATTERNS
from .masking import HMACMasking, SimpleMasking

__all__ = [
    "RedactionEngine",
    "RedactionMode",
    "CLOUDS_AND_PII_PATTERNS",
    "HMACMasking",
    "SimpleMasking",
]
