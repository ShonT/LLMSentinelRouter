#!/usr/bin/env python3
"""
Migration script for updating existing UnifiedConfig JSON to the new schema.
Adds missing fields (model_definition, model_key, free_tier_limits, paid_tier_limits, cost)
and ensures judge_config and routing_order_config exist.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add the project root to sys.path to import sentinelrouter modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sentinelrouter.schemas.config_models import (
    UnifiedConfig,
    ModelConfig,
    TierLimits,
    CostInfo,
    JudgeConfig,
    RoutingOrderConfig,
)


def migrate_config(input_path: str, output_path: str = None):
    """
    Load a UnifiedConfig JSON file, upgrade it to the latest schema,
    and write the upgraded version back.

    Args:
        input_path: Path to the existing config file.
        output_path: Path to write the upgraded config (default: same as input_path).
    """
    if output_path is None:
        output_path = input_path

    with open(input_path, 'r') as f:
        data = json.load(f)

    # Ensure each model has a model_key (set to its dict key) and other missing fields
    models = data.get('models', {})
    for model_id, model_data in models.items():
        # Set model_key if missing
        if 'model_key' not in model_data:
            model_data['model_key'] = model_id
        # Set model_definition if missing
        if 'model_definition' not in model_data:
            model_data['model_definition'] = f"Model {model_id}"
        # Ensure free_tier_limits and paid_tier_limits exist
        if 'free_tier_limits' not in model_data:
            # Default free tier limits (copy from limits or use defaults)
            limits = model_data.get('limits', {})
            model_data['free_tier_limits'] = {
                'requests_per_day': limits.get('requests_per_day', 1500),
                'requests_per_minute': limits.get('requests_per_minute', 15),
                'tokens_per_minute': limits.get('tokens_per_minute', 1_000_000),
                'tokens_per_day': limits.get('tokens_per_day', 10_000_000),
            }
        if 'paid_tier_limits' not in model_data:
            # Default paid tier limits (higher than free)
            model_data['paid_tier_limits'] = {
                'requests_per_day': 10000,
                'requests_per_minute': 100,
                'tokens_per_minute': 10_000_000,
                'tokens_per_day': 100_000_000,
            }
        # Ensure cost exists
        if 'cost' not in model_data:
            model_data['cost'] = {
                'per_call': 0.0,
                'per_token_input': 0.0,
                'per_token_output': 0.0,
            }

    # Ensure judge_config exists
    if 'judge_config' not in data:
        data['judge_config'] = {
            'model_order': [],
            'is_judge_required': False,
        }

    # Ensure routing_order_config exists
    if 'routing_order_config' not in data:
        data['routing_order_config'] = {
            'strong_models': [],
            'weak_models': [],
        }

    # Validate the entire config using UnifiedConfig to fill any remaining defaults
    config = UnifiedConfig(**data)

    # Write back
    with open(output_path, 'w') as f:
        json.dump(config.dict(), f, indent=2, default=str)

    print(f"Migration successful. Upgraded config written to {output_path}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description="Migrate UnifiedConfig JSON to latest schema"
    )
    parser.add_argument(
        '--input', default='config/models_config.json',
        help='Input config file path (default: config/models_config.json)'
    )
    parser.add_argument(
        '--output',
        help='Output config file path (default: same as input, overwrites)'
    )
    args = parser.parse_args()

    migrate_config(args.input, args.output)