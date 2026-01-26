"""
SentinelRouter - Intelligent budget-aware routing between LLM providers.
"""

__version__ = "0.1.0"
__author__ = "SentinelRouter Team"
__description__ = "Production-ready local API gateway for budget‑controlled LLM routing"

from .sentinelrouter.server import app
from .sentinelrouter.router_logic import Router
from .sentinelrouter.config import get_settings

__all__ = ["app", "Router", "get_settings"]
