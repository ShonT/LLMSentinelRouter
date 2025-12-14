import pytest
import os

# Set mock API keys as environment variables before any imports
# This ensures Settings validation passes during test collection
os.environ["DEEPSEEK_API_KEY"] = "mock-deepseek-key"
os.environ["ANTHROPIC_API_KEY"] = "mock-anthropic-key"

from sentinelrouter.sentinelrouter.config import get_settings