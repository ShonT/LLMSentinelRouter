#!/usr/bin/env python3
"""
Simple demo script for backup judges - can be run directly in Docker or locally.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now run the tests
import asyncio
from tests.test_backup_judges_demo import run_all_tests

if __name__ == "__main__":
    asyncio.run(run_all_tests())
