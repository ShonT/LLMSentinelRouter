"""
Comprehensive pattern registry for sensitive data detection.

Includes patterns for:
- Cloud providers (AWS, GCP, Azure)
- PII (SSN, credit cards, phone numbers)
- Database credentials
- API keys and tokens
"""

import re
from typing import List, NamedTuple


class RedactionPattern(NamedTuple):
    """A named pattern for detecting sensitive data."""

    name: str
    regex: re.Pattern
    description: str
    group_name: str = (
        None  # Optional: specific group to redact (e.g., password in connection string)
    )


# Comprehensive Pattern Registry
CLOUDS_AND_PII_PATTERNS: List[RedactionPattern] = [
    # --- AMAZON WEB SERVICES (AWS) ---
    RedactionPattern(
        "AWS Access Key ID",
        re.compile(
            r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"
        ),
        "Matches AWS Access Key IDs",
    ),
    RedactionPattern(
        "AWS Secret Access Key",
        re.compile(r"(?i)aws(.{0,20})?secret(.{0,20})?['\"][0-9a-zA-Z/+=]{40}['\"]"),
        "Matches AWS Secret Access Keys",
    ),
    RedactionPattern(
        "AWS Session Token",
        re.compile(
            r"(?i)aws(.{0,20})?session(.{0,20})?token(.{0,20})?['\"][A-Za-z0-9/+=]{100,500}['\"]"
        ),
        "Matches AWS temporary session tokens",
    ),
    # --- GOOGLE CLOUD PLATFORM (GCP) ---
    RedactionPattern(
        "GCP API Key",
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        "Matches Google Cloud and Firebase API keys",
    ),
    RedactionPattern(
        "GCP OAuth Client ID",
        re.compile(r"[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com"),
        "Matches Google OAuth 2.0 Client IDs",
    ),
    RedactionPattern(
        "GCP Service Account Key",
        re.compile(
            r'"type":\s*"service_account"[^}]{100,1000}"private_key":\s*"[^"]{1,2000}"'
        ),
        "Matches GCP service account JSON key files",
    ),
    # --- MICROSOFT AZURE ---
    RedactionPattern(
        "Azure Storage Key",
        re.compile(
            r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[a-zA-Z0-9+/=]{88};"
        ),
        "Matches Azure Storage connection strings",
    ),
    RedactionPattern(
        "Azure Client Secret",
        re.compile(
            r"(?i)azure(.{0,20})?client.?secret(.{0,20})?['\"\s][a-zA-Z0-9.~_-]{32,}['\"]"
        ),
        "Matches Azure AD App client secrets",
    ),
    RedactionPattern(
        "Azure Subscription Key",
        re.compile(
            r"(?i)(?:ocp-apim-subscription-key|api-key)(.{0,10})?['\"\s][a-f0-9]{32}['\"]"
        ),
        "Matches Azure API Management subscription keys",
    ),
    # --- PII (Personally Identifiable Information) ---
    RedactionPattern(
        "US SSN",
        # Ensures first block isn't 000, 666, or 900+
        re.compile(
            r"\b(?!000|666|9\d{2})([0-8]\d{2}|7([0-6]\d))([- ]?)(?!00)\d\d\3(?!0000)\d{4}\b"
        ),
        "Matches US Social Security Numbers with/without delimiters",
    ),
    RedactionPattern(
        "Credit Card",
        re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"  # Visa
            r"5[1-5][0-9]{14}|"  # Mastercard
            r"6(?:011|5[0-9][0-9])[0-9]{12}|"  # Discover
            r"3[47][0-9]{13}|"  # Amex
            r"3(?:0[0-5]|[68][0-9])[0-9]{11}|"  # Diners
            r"(?:2131|1800|35\d{3})\d{11})\b"  # JCB
        ),
        "Matches major credit card formats (Visa, MC, Amex, Discover, Diners, JCB)",
    ),
    RedactionPattern(
        "US Phone Number",
        re.compile(
            r"\b(?:\+?1[-.\s]?)?\(?([2-9][0-9]{2})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b"
        ),
        "Matches US phone numbers with various formats",
    ),
    RedactionPattern(
        "Email Address",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "Matches email addresses",
    ),
    RedactionPattern(
        "IPv4 Address",
        re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
        "Matches IPv4 addresses",
    ),
    # --- DATABASE CONNECTION STRINGS ---
    RedactionPattern(
        "PostgreSQL Connection",
        re.compile(
            r"postgres(?:ql)?://(?P<user>[^:]+):(?P<pass>[^@]+)@(?P<host>[^/:]+)(?::(?P<port>\d+))?/(?P<db>[^\s?]+)"
        ),
        "Matches PostgreSQL connection strings",
        group_name="pass",  # Only redact the password group
    ),
    RedactionPattern(
        "MySQL Connection",
        re.compile(
            r"mysql://(?P<user>[^:]+):(?P<pass>[^@]+)@(?P<host>[^/:]+)(?::(?P<port>\d+))?/(?P<db>[^\s?]+)"
        ),
        "Matches MySQL connection strings",
        group_name="pass",
    ),
    RedactionPattern(
        "MongoDB Connection",
        re.compile(
            r"mongodb(?:\+srv)?://(?P<user>[^:]+):(?P<pass>[^@]+)@(?P<host>[^/?]+)"
        ),
        "Matches MongoDB connection strings",
        group_name="pass",
    ),
    # --- GENERIC SECRETS ---
    RedactionPattern(
        "Generic API Key",
        re.compile(
            r"(?i)(?:api[_-]?key|apikey)(.{0,10})?['\"\s]([a-zA-Z0-9_\-]{20,})['\"]"
        ),
        "Matches generic API key patterns",
    ),
    RedactionPattern(
        "Bearer Token",
        re.compile(r"(?i)bearer\s+([a-zA-Z0-9_\-\.=+/]{20,})"),
        "Matches Bearer tokens in Authorization headers",
    ),
    RedactionPattern(
        "Private Key",
        re.compile(
            r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[^-]+-----END (?:RSA |EC )?PRIVATE KEY-----"
        ),
        "Matches PEM-encoded private keys",
    ),
    # --- VERSION CONTROL TOKENS ---
    RedactionPattern(
        "GitHub Token",
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),
        "Matches GitHub personal access tokens, OAuth tokens, etc.",
    ),
    RedactionPattern(
        "GitLab Token",
        re.compile(r"glpat-[a-zA-Z0-9\-_]{20,}"),
        "Matches GitLab personal access tokens",
    ),
    # --- SLACK ---
    RedactionPattern(
        "Slack Token",
        re.compile(r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}"),
        "Matches Slack API tokens",
    ),
    RedactionPattern(
        "Slack Webhook",
        re.compile(
            r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+"
        ),
        "Matches Slack incoming webhook URLs",
    ),
]


# Category groupings for easier management
PATTERN_CATEGORIES = {
    "AWS": ["AWS Access Key ID", "AWS Secret Access Key", "AWS Session Token"],
    "GCP": ["GCP API Key", "GCP OAuth Client ID", "GCP Service Account Key"],
    "Azure": ["Azure Storage Key", "Azure Client Secret", "Azure Subscription Key"],
    "PII": [
        "US SSN",
        "Credit Card",
        "US Phone Number",
        "Email Address",
        "IPv4 Address",
    ],
    "Database": ["PostgreSQL Connection", "MySQL Connection", "MongoDB Connection"],
    "Generic": ["Generic API Key", "Bearer Token", "Private Key"],
    "VCS": ["GitHub Token", "GitLab Token"],
    "Collaboration": ["Slack Token", "Slack Webhook"],
}


def get_patterns_by_category(category: str) -> List[RedactionPattern]:
    """Get all patterns for a specific category."""
    pattern_names = PATTERN_CATEGORIES.get(category, [])
    return [p for p in CLOUDS_AND_PII_PATTERNS if p.name in pattern_names]


def get_all_categories() -> List[str]:
    """Get list of all pattern categories."""
    return list(PATTERN_CATEGORIES.keys())
