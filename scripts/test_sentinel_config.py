#!/usr/bin/env python3
"""
Test script for the new Pydantic configuration schema.
Tests both valid and invalid configurations to ensure proper validation.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly from the schema module to avoid triggering server initialization
import importlib.util
spec = importlib.util.spec_from_file_location(
    "sentinel_config", 
    Path(__file__).parent.parent / "sentinelrouter" / "schemas" / "sentinel_config.py"
)
sentinel_config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sentinel_config_module)

SentinelConfig = sentinel_config_module.SentinelConfig
ProviderType = sentinel_config_module.ProviderType
Key = sentinel_config_module.Key
KeyInstance = sentinel_config_module.KeyInstance
ModelDefinition = sentinel_config_module.ModelDefinition
Pricing = sentinel_config_module.Pricing
Limits = sentinel_config_module.Limits
RoutingPolicy = sentinel_config_module.RoutingPolicy
RoutingTier = sentinel_config_module.RoutingTier
JudgeConfig = sentinel_config_module.JudgeConfig
SemanticCacheConfig = sentinel_config_module.SemanticCacheConfig


def print_test_header(test_name: str):
    """Print a formatted test header."""
    print("\n" + "=" * 70)
    print(f"TEST: {test_name}")
    print("=" * 70)


def print_success(message: str):
    """Print a success message."""
    print(f"✅ SUCCESS: {message}")


def print_failure(message: str):
    """Print a failure message."""
    print(f"❌ FAILURE: {message}")


def print_expected_error(message: str):
    """Print an expected error message."""
    print(f"✅ EXPECTED ERROR: {message}")


# ============================================================================
# Valid Configuration Tests
# ============================================================================

def test_valid_minimal_config():
    """Test a minimal valid configuration."""
    print_test_header("Valid Minimal Configuration")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "llama-3.1-8b-instant",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {
                    "requests_per_minute": 30,
                    "requests_per_day": 1000,
                    "tokens_per_minute": 30000
                }
            },
            "model2": {
                "enabled": True,
                "provider": "groq",
                "model_id": "llama-3.1-70b",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.59, "output_cost_per_m": 0.79},
                "limits": {
                    "requests_per_minute": 30,
                    "requests_per_day": 1000,
                    "tokens_per_minute": 30000
                }
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model2"]}
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_success("Minimal configuration loaded successfully")
        print(f"  - Models: {list(config.models.keys())}")
        print(f"  - Weak tier: {config.routing_policy.weak_tier.order}")
        print(f"  - Strong tier: {config.routing_policy.strong_tier.order}")
        return True
    except Exception as e:
        print_failure(f"Unexpected error: {e}")
        return False


def test_valid_demo_config():
    """Test loading the demo configuration file."""
    print_test_header("Valid Demo Configuration from File")
    
    config_path = Path(__file__).parent.parent / "config" / "sentinel_config_demo.json"
    
    if not config_path.exists():
        print_failure(f"Demo config not found at {config_path}")
        return False
    
    try:
        with open(config_path, "r") as f:
            config_dict = json.load(f)
        
        config = SentinelConfig(**config_dict)
        print_success("Demo configuration loaded successfully")
        print(f"  - Keys: {list(config.keys.keys())}")
        print(f"  - Key instances: {list(config.key_instances.keys())}")
        print(f"  - Models: {list(config.models.keys())}")
        print(f"  - Weak tier: {config.routing_policy.weak_tier.order}")
        print(f"  - Strong tier: {config.routing_policy.strong_tier.order}")
        print(f"  - Judge enabled: {config.judge.enabled}")
        print(f"  - Judge models: {config.judge.model_order}")
        print(f"  - Semantic cache enabled: {config.semantic_cache.enabled}")
        return True
    except Exception as e:
        print_failure(f"Unexpected error: {e}")
        return False


def test_valid_disabled_model():
    """Test that disabled models work correctly."""
    print_test_header("Valid Configuration with Disabled Model")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model2": {
                "enabled": False,  # Disabled
                "provider": "groq",
                "model_id": "model2",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model3": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model3",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.10, "output_cost_per_m": 0.15},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},  # Only enabled models
            "strong_tier": {"order": ["model3"]}
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_success("Configuration with disabled model loaded successfully")
        print(f"  - Model1 enabled: {config.models['model1'].enabled}")
        print(f"  - Model2 enabled: {config.models['model2'].enabled}")
        print(f"  - Model3 enabled: {config.models['model3'].enabled}")
        return True
    except Exception as e:
        print_failure(f"Unexpected error: {e}")
        return False


# ============================================================================
# Invalid Configuration Tests
# ============================================================================

def test_invalid_missing_key():
    """Test that missing key reference is caught."""
    print_test_header("Invalid: KeyInstance refers to missing key")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "nonexistent_key"}  # BAD
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model1"]}
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for missing key")
        return False
    except ValueError as e:
        if "refers to missing key" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_missing_key_instance():
    """Test that missing key instance is caught."""
    print_test_header("Invalid: Model refers to missing key instance")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "nonexistent_instance",  # BAD
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model1"]}
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for missing key instance")
        return False
    except ValueError as e:
        if "refers to missing key_instance" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_provider_mismatch():
    """Test that provider type mismatch is caught."""
    print_test_header("Invalid: Model provider doesn't match key provider")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "anthropic",  # BAD - doesn't match key type
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model1"]}
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for provider mismatch")
        return False
    except ValueError as e:
        if "does not match" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_empty_tier():
    """Test that empty routing tier is caught."""
    print_test_header("Invalid: Empty routing tier")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": []},  # BAD - empty
            "strong_tier": {"order": ["model1"]}
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for empty tier")
        return False
    except ValueError as e:
        if "must not be empty" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_tier_missing_model():
    """Test that routing tier referring to missing model is caught."""
    print_test_header("Invalid: Routing tier refers to missing model")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["nonexistent_model"]}  # BAD
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for missing model in tier")
        return False
    except ValueError as e:
        if "refers to missing model" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_tier_disabled_model():
    """Test that routing tier referring to disabled model is caught."""
    print_test_header("Invalid: Routing tier refers to disabled model")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model2": {
                "enabled": False,  # Disabled
                "provider": "groq",
                "model_id": "model2",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model2"]}  # BAD - model2 is disabled
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for disabled model in tier")
        return False
    except ValueError as e:
        if "refers to disabled model" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_tier_overlap():
    """Test that overlapping tiers are caught."""
    print_test_header("Invalid: Model appears in both weak and strong tiers")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model2": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model2",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.10, "output_cost_per_m": 0.15},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1", "model2"]},
            "strong_tier": {"order": ["model2"]}  # BAD - model2 in both tiers
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for tier overlap")
        return False
    except ValueError as e:
        if "cannot appear in both" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_judge_enabled_empty_order():
    """Test that enabled judge with empty model order is caught."""
    print_test_header("Invalid: Judge enabled but model_order is empty")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model2": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model2",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.10, "output_cost_per_m": 0.15},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model2"]}
        },
        "judge": {
            "enabled": True,
            "model_order": []  # BAD - empty when enabled
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for empty judge model_order")
        return False
    except ValueError as e:
        if "judge.model_order is empty" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_invalid_judge_missing_model():
    """Test that judge referring to missing model is caught."""
    print_test_header("Invalid: Judge refers to missing model")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model2": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model2",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.10, "output_cost_per_m": 0.15},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model2"]}
        },
        "judge": {
            "enabled": True,
            "model_order": ["nonexistent_model"]  # BAD
        }
    }
    
    try:
        config = SentinelConfig(**config_dict)
        print_failure("Should have raised ValueError for missing model in judge")
        return False
    except ValueError as e:
        if "judge.model_order refers to missing model" in str(e):
            print_expected_error(f"Caught expected error: {e}")
            return True
        else:
            print_failure(f"Wrong error: {e}")
            return False


def test_warning_cache_without_judge():
    """Test that semantic cache without judge produces a warning."""
    print_test_header("Warning: Semantic cache enabled without judge")
    
    config_dict = {
        "keys": {
            "key1": {"type": "groq", "value": "test-key"}
        },
        "key_instances": {
            "groq_primary": {"key_ref": "key1"}
        },
        "models": {
            "model1": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model1",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.05, "output_cost_per_m": 0.08},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            },
            "model2": {
                "enabled": True,
                "provider": "groq",
                "model_id": "model2",
                "key_instance": "groq_primary",
                "pricing": {"input_cost_per_m": 0.10, "output_cost_per_m": 0.15},
                "limits": {"requests_per_minute": 30, "requests_per_day": 1000, "tokens_per_minute": 30000}
            }
        },
        "routing_policy": {
            "weak_tier": {"order": ["model1"]},
            "strong_tier": {"order": ["model2"]}
        },
        "judge": {
            "enabled": False
        },
        "semantic_cache": {
            "enabled": True  # Enabled without judge
        }
    }
    
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            config = SentinelConfig(**config_dict)
            if len(w) > 0 and "semantic_cache" in str(w[0].message):
                print_expected_error(f"Caught expected warning: {w[0].message}")
                return True
            else:
                print_failure("Warning not raised")
                return False
        except Exception as e:
            print_failure(f"Unexpected error: {e}")
            return False


# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("SENTINEL ROUTER CONFIGURATION VALIDATION TESTS")
    print("=" * 70)
    
    valid_tests = [
        test_valid_minimal_config,
        test_valid_demo_config,
        test_valid_disabled_model,
    ]
    
    invalid_tests = [
        test_invalid_missing_key,
        test_invalid_missing_key_instance,
        test_invalid_provider_mismatch,
        test_invalid_empty_tier,
        test_invalid_tier_missing_model,
        test_invalid_tier_disabled_model,
        test_invalid_tier_overlap,
        test_invalid_judge_enabled_empty_order,
        test_invalid_judge_missing_model,
        test_warning_cache_without_judge,
    ]
    
    results = {
        "valid": {"passed": 0, "failed": 0, "total": len(valid_tests)},
        "invalid": {"passed": 0, "failed": 0, "total": len(invalid_tests)},
    }
    
    # Run valid tests
    print("\n\n" + "=" * 70)
    print("VALID CONFIGURATION TESTS")
    print("=" * 70)
    
    for test in valid_tests:
        if test():
            results["valid"]["passed"] += 1
        else:
            results["valid"]["failed"] += 1
    
    # Run invalid tests
    print("\n\n" + "=" * 70)
    print("INVALID CONFIGURATION TESTS")
    print("=" * 70)
    
    for test in invalid_tests:
        if test():
            results["invalid"]["passed"] += 1
        else:
            results["invalid"]["failed"] += 1
    
    # Print summary
    print("\n\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    print(f"\nValid Configuration Tests:")
    print(f"  Passed: {results['valid']['passed']}/{results['valid']['total']}")
    print(f"  Failed: {results['valid']['failed']}/{results['valid']['total']}")
    
    print(f"\nInvalid Configuration Tests:")
    print(f"  Passed: {results['invalid']['passed']}/{results['invalid']['total']}")
    print(f"  Failed: {results['invalid']['failed']}/{results['invalid']['total']}")
    
    total_passed = results['valid']['passed'] + results['invalid']['passed']
    total_tests = results['valid']['total'] + results['invalid']['total']
    
    print(f"\nOverall: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total_tests - total_passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
