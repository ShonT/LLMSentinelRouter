#!/usr/bin/env python3
"""
Simple configuration validation tool for SentinelRouter.
Usage: python scripts/validate_config.py <config_file.json>
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly from schema to avoid server initialization
import importlib.util
spec = importlib.util.spec_from_file_location(
    "sentinel_config",
    Path(__file__).parent.parent / "sentinelrouter" / "schemas" / "sentinel_config.py"
)
sentinel_config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sentinel_config_module)

SentinelConfig = sentinel_config_module.SentinelConfig


def validate_config_file(config_path: str) -> bool:
    """
    Validate a configuration file and print detailed results.
    
    Args:
        config_path: Path to the JSON configuration file
        
    Returns:
        True if valid, False otherwise
    """
    path = Path(config_path)
    
    if not path.exists():
        print(f"❌ Error: File not found: {config_path}")
        return False
    
    if not path.suffix == ".json":
        print(f"⚠️  Warning: File doesn't have .json extension: {config_path}")
    
    print(f"📄 Validating configuration: {config_path}")
    print("=" * 70)
    
    try:
        # Load JSON
        with open(path, "r") as f:
            config_dict = json.load(f)
        
        print("✅ JSON syntax is valid")
        
        # Validate with Pydantic
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = SentinelConfig(**config_dict)
            
            # Report warnings
            if w:
                print("\n⚠️  Warnings:")
                for warning in w:
                    print(f"   - {warning.message}")
        
        # Print summary
        print("\n✅ Configuration is VALID!")
        print("=" * 70)
        print("\nConfiguration Summary:")
        print(f"  Keys: {len(config.keys)}")
        print(f"  Key Instances: {len(config.key_instances)}")
        print(f"  Models: {len(config.models)}")
        
        enabled_models = [m for m in config.models.values() if m.enabled]
        disabled_models = [m for m in config.models.values() if not m.enabled]
        
        print(f"    - Enabled: {len(enabled_models)}")
        if disabled_models:
            print(f"    - Disabled: {len(disabled_models)}")
        
        print(f"  Weak Tier: {len(config.routing_policy.weak_tier.order)} models")
        for model_id in config.routing_policy.weak_tier.order:
            model = config.models[model_id]
            print(f"    - {model_id} ({model.display_name or model.model_id})")
        
        print(f"  Strong Tier: {len(config.routing_policy.strong_tier.order)} models")
        for model_id in config.routing_policy.strong_tier.order:
            model = config.models[model_id]
            print(f"    - {model_id} ({model.display_name or model.model_id})")
        
        if config.judge.enabled:
            print(f"  Judge: ENABLED ({len(config.judge.model_order)} models)")
            for model_id in config.judge.model_order:
                print(f"    - {model_id}")
        else:
            print("  Judge: DISABLED")
        
        if config.semantic_cache.enabled:
            print(f"  Semantic Cache: ENABLED")
            print(f"    - Min samples: {config.semantic_cache.min_samples}")
            print(f"    - Confidence threshold: {config.semantic_cache.confidence_threshold}")
        else:
            print("  Semantic Cache: DISABLED")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error:")
        print(f"   Line {e.lineno}, Column {e.colno}: {e.msg}")
        return False
        
    except ValueError as e:
        print(f"\n❌ Configuration Validation FAILED!")
        print("=" * 70)
        print(f"\nError: {e}")
        print("\nPlease fix the error and try again.")
        print("See documentation/configuration/pydantic-config.md for help.")
        return False
        
    except Exception as e:
        print(f"\n❌ Unexpected Error!")
        print("=" * 70)
        print(f"Error: {e}")
        return False


def main():
    if len(sys.argv) != 2:
        print("Usage: python validate_config.py <config_file.json>")
        print("\nExample:")
        print("  python validate_config.py config/sentinel_config_demo.json")
        sys.exit(1)
    
    config_path = sys.argv[1]
    success = validate_config_file(config_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
