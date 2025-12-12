#!/usr/bin/env python3
"""
Migration script to transition from the legacy SQLite-based configuration
to the new unified JSON configuration with write‑behind persistence.

This script:
1. Reads the existing environment variables and SQLite database (if any)
2. Creates a new `models_config.json` with the extracted settings
3. Initializes the StateManager with any existing usage data
4. Optionally archives the old SQLite database for backup
"""

import asyncio
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

# Ensure we can import sentinelrouter modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentinelrouter.schemas.config_models import (
    SystemSettings,
    ModelCapabilities,
    RoutingConfig,
    RateLimits,
    PricingTier,
    PricingInfo,
    ModelState,
    ModelConfig,
    UnifiedConfig,
)
from sentinelrouter.sentinelrouter.config import get_settings, get_unified_config
from sentinelrouter.sentinelrouter.state_manager import get_state_manager


class MigrationManager:
    def __init__(self):
        self.workspace = Path("/Users/shonhitwork/Documents/unstuckRouter")
        self.config_path = self.workspace / "config" / "models_config.json"
        self.backup_dir = self.workspace / "config" / "backups"
        self.db_path = self.workspace / "sentinelrouter" / "database.db"
        self.env_settings = get_settings()
        self.new_config = None

    def backup_existing_config(self) -> str:
        """Create a timestamped backup of the current JSON config."""
        self.backup_dir.mkdir(exist_ok=True)
        if self.config_path.exists():
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"models_config_{timestamp}.json"
            backup_path = self.backup_dir / backup_name
            shutil.copy2(self.config_path, backup_path)
            return str(backup_path)
        return ""

    def load_legacy_database(self) -> Dict[str, Any]:
        """Extract any useful state from the SQLite database."""
        if not self.db_path.exists():
            return {}

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get total request counts per model from routing_decisions
        cursor.execute("""
            SELECT model_used, COUNT(*) as count, SUM(cost_incurred) as total_cost
            FROM routing_decisions
            WHERE created_at >= date('now', 'start of day')
            GROUP BY model_used
        """)
        rows = cursor.fetchall()

        daily_usage = {}
        for row in rows:
            daily_usage[row["model_used"]] = {
                "requests_today": row["count"],
                "total_cost_today": row["total_cost"] or 0.0,
            }

        # Get session costs for resetting
        cursor.execute("SELECT session_id, current_cost FROM sessions")
        session_costs = {row["session_id"]: row["current_cost"] for row in cursor.fetchall()}

        conn.close()

        return {
            "daily_usage": daily_usage,
            "session_costs": session_costs,
            "db_exists": True,
        }

    def create_default_models(self) -> Dict[str, ModelConfig]:
        """Build the new model configurations from environment variables."""
        models = {}

        # DeepSeek Chat
        models["deepseek-chat"] = ModelConfig(
            display_name="DeepSeek Chat",
            provider="deepseek",
            status="active" if self.env_settings.deepseek_api_key else "disabled",
            capabilities=ModelCapabilities(
                modality=["text"],
                context_window=128000,
            ),
            routing=RoutingConfig(
                priority_group="fast_tier",
                order=1,
            ),
            limits=RateLimits(
                requests_per_minute=15,
                requests_per_day=1500,
                tokens_per_minute=1_000_000,
            ),
            pricing=PricingInfo(
                currency="USD",
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                usage_tiers=[
                    PricingTier(
                        name="Free Tier",
                        threshold_requests=1500,
                        input_cost=0.0,
                        output_cost=0.0,
                    ),
                    PricingTier(
                        name="Paid Tier",
                        threshold_requests="inf",
                        input_cost=0.35,
                        output_cost=0.70,
                    ),
                ],
            ),
            state=ModelState(
                current_rpm=0,
                requests_today=0,
                tokens_today=0,
                total_cost_session=0.0,
                last_updated_ts=None,
                exhausted_until_ts=None,
            ),
        )

        # Claude Opus
        models["claude-3-opus-20240229"] = ModelConfig(
            display_name="Claude 3 Opus",
            provider="anthropic",
            status="active" if self.env_settings.anthropic_api_key else "disabled",
            capabilities=ModelCapabilities(
                modality=["text"],
                context_window=200000,
            ),
            routing=RoutingConfig(
                priority_group="strong_tier",
                order=1,
            ),
            limits=RateLimits(
                requests_per_minute=8,
                requests_per_day=800,
                tokens_per_minute=400_000,
            ),
            pricing=PricingInfo(
                currency="USD",
                input_cost_per_m=15.0,
                output_cost_per_m=75.0,
                usage_tiers=[
                    PricingTier(
                        name="Standard",
                        threshold_requests="inf",
                        input_cost=15.0,
                        output_cost=75.0,
                    ),
                ],
            ),
            state=ModelState(
                current_rpm=0,
                requests_today=0,
                tokens_today=0,
                total_cost_session=0.0,
                last_updated_ts=None,
                exhausted_until_ts=None,
            ),
        )

        # Gemini 2.5 Flash
        models["gemini-2.5-flash"] = ModelConfig(
            display_name="Gemini 2.5 Flash",
            provider="google",
            status="active" if self.env_settings.gemini_api_key else "disabled",
            capabilities=ModelCapabilities(
                modality=["text", "image"],
                context_window=1_000_000,
            ),
            routing=RoutingConfig(
                priority_group="fast_tier",
                order=2,
            ),
            limits=RateLimits(
                requests_per_minute=20,
                requests_per_day=2000,
                tokens_per_minute=2_000_000,
            ),
            pricing=PricingInfo(
                currency="USD",
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                usage_tiers=[
                    PricingTier(
                        name="Free Tier",
                        threshold_requests=2000,
                        input_cost=0.0,
                        output_cost=0.0,
                    ),
                    PricingTier(
                        name="Paid Tier",
                        threshold_requests="inf",
                        input_cost=0.35,
                        output_cost=0.70,
                    ),
                ],
            ),
            state=ModelState(
                current_rpm=0,
                requests_today=0,
                tokens_today=0,
                total_cost_session=0.0,
                last_updated_ts=None,
                exhausted_until_ts=None,
            ),
        )

        # Gemini Flash Lite
        models["gemini-2.5-flash-lite"] = ModelConfig(
            display_name="Gemini 2.5 Flash Lite",
            provider="google",
            status="active" if self.env_settings.gemini_api_key else "disabled",
            capabilities=ModelCapabilities(
                modality=["text"],
                context_window=1_000_000,
            ),
            routing=RoutingConfig(
                priority_group="fast_tier",
                order=3,
            ),
            limits=RateLimits(
                requests_per_minute=30,
                requests_per_day=3000,
                tokens_per_minute=3_000_000,
            ),
            pricing=PricingInfo(
                currency="USD",
                input_cost_per_m=0.0,
                output_cost_per_m=0.0,
                usage_tiers=[
                    PricingTier(
                        name="Free Tier",
                        threshold_requests=3000,
                        input_cost=0.0,
                        output_cost=0.0,
                    ),
                ],
            ),
            state=ModelState(
                current_rpm=0,
                requests_today=0,
                tokens_today=0,
                total_cost_session=0.0,
                last_updated_ts=None,
                exhausted_until_ts=None,
            ),
        )

        return models

    def apply_legacy_usage(self, models: Dict[str, ModelConfig], legacy_data: Dict[str, Any]):
        """Update model states with any historical usage from the old database."""
        daily_usage = legacy_data.get("daily_usage", {})
        for model_id, model_config in models.items():
            if model_id in daily_usage:
                usage = daily_usage[model_id]
                model_config.state.requests_today = usage.get("requests_today", 0)
                model_config.state.total_cost_session = usage.get("total_cost_today", 0.0)
                model_config.state.last_updated_ts = datetime.utcnow()

    def build_unified_config(self, legacy_data: Dict[str, Any]) -> UnifiedConfig:
        """Create the new unified configuration."""
        system_settings = SystemSettings(
            persistence_interval_seconds=5,
            default_routing_strategy="waterfall",
            timezone="UTC",
        )

        models = self.create_default_models()
        self.apply_legacy_usage(models, legacy_data)

        return UnifiedConfig(
            system_settings=system_settings,
            models=models,
        )

    async def write_config_and_initialize(self, unified_config: UnifiedConfig):
        """Write the new JSON config and initialize the StateManager."""
        # Ensure config directory exists
        self.config_path.parent.mkdir(exist_ok=True)

        # Convert to dict, excluding None values
        config_dict = unified_config.dict(exclude_none=True)

        # Write JSON with pretty formatting
        with open(self.config_path, "w") as f:
            json.dump(config_dict, f, indent=2, default=str)

        print(f"✅ Created new configuration at {self.config_path}")

        # Initialize StateManager with the new config
        state_manager = await get_state_manager()
        print("✅ StateManager initialized with migrated configuration")

        # Optionally, we could pre‑populate the state with legacy data
        # but the StateManager already loads from the file we just wrote.

    def archive_old_database(self):
        """Move the old SQLite database to a backup location."""
        if not self.db_path.exists():
            return

        archive_dir = self.workspace / "database_archive"
        archive_dir.mkdir(exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"database_{timestamp}.db"
        shutil.move(self.db_path, archive_path)
        print(f"📦 Archived old database to {archive_path}")

    def print_summary(self, unified_config: UnifiedConfig, legacy_data: Dict[str, Any]):
        """Print a human‑readable migration summary."""
        print("\n" + "=" * 60)
        print("SENTINELROUTER CONFIGURATION MIGRATION SUMMARY")
        print("=" * 60)

        print(f"\n📁 Configuration written to: {self.config_path}")
        print(f"📦 Legacy database backed up: {legacy_data.get('db_exists', False)}")

        print("\n🧠 Models migrated:")
        for model_id, model_cfg in unified_config.models.items():
            status = model_cfg.status
            key_present = "✅" if status == "active" else "❌"
            print(f"  {key_present} {model_id:30} [{status:>8}] "
                  f"priority={model_cfg.routing.priority_group:12} order={model_cfg.routing.order}")

        daily_usage = legacy_data.get("daily_usage", {})
        if daily_usage:
            print("\n📊 Imported daily usage from legacy database:")
            for model, usage in daily_usage.items():
                print(f"  {model:30} requests={usage.get('requests_today', 0):4d} "
                      f"cost=${usage.get('total_cost_today', 0.0):.4f}")

        print("\n⚙️ System settings:")
        print(f"  Persistence interval: {unified_config.system_settings.persistence_interval_seconds}s")
        print(f"  Default routing: {unified_config.system_settings.default_routing_strategy}")
        print(f"  Timezone: {unified_config.system_settings.timezone}")

        print("\n🚀 Next steps:")
        print("  1. Restart the SentinelRouter server")
        print("  2. Verify the new dashboard at http://localhost:8001")
        print("  3. Review the configuration in the 'Configuration & Keys' tab")
        print("=" * 60)

    async def run(self, archive_old_db: bool = False):
        """Execute the full migration pipeline."""
        print("🔄 Starting migration from SQLite to unified JSON configuration...")

        # Step 1: Backup existing config
        backup = self.backup_existing_config()
        if backup:
            print(f"📂 Backed up previous config to {backup}")

        # Step 2: Extract legacy data
        legacy_data = self.load_legacy_database()
        if legacy_data.get("db_exists"):
            print("🗃️  Found legacy SQLite database, extracting usage data...")

        # Step 3: Build new unified configuration
        unified_config = self.build_unified_config(legacy_data)

        # Step 4: Write config and initialize StateManager
        await self.write_config_and_initialize(unified_config)

        # Step 5: Optionally archive the old database
        if archive_old_db:
            self.archive_old_database()

        # Step 6: Print summary
        self.print_summary(unified_config, legacy_data)


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate SentinelRouter configuration to unified JSON format.")
    parser.add_argument(
        "--archive-db",
        action="store_true",
        help="Archive the old SQLite database after migration (recommended for production)"
    )
    parser.add_argument(
        "--no-archive",
        action="store_false",
        dest="archive_db",
        help="Keep the old SQLite database (for debugging)"
    )
    parser.set_defaults(archive_db=True)

    args = parser.parse_args()

    migrator = MigrationManager()
    try:
        await migrator.run(archive_old_db=args.archive_db)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())