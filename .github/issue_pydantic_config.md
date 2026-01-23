Excellent — this is the right time to **lock the schema**.
Below is a **surgically updated version** of your Pydantic config that:

* Implements **all 5 of your requirements**
* Adds **only the necessary validation logic** (no overreach)
* Includes **operator-facing comments** directly in the schema (via `Field(description=...)`)
* Preserves your original structure and intent

I’ll present:

1. **Updated models (only where changed)**
2. **Exact updated validator code**
3. **Why each validation exists (operator intent)**

---

# 1️⃣ Schema updates (annotated, operator-facing)

### 🔧 ModelDefinition — add `enabled`

```python
class ModelDefinition(BaseModel):
    """
    A concrete executable model definition.
    A model is uniquely identified by (provider, model_id, key_instance).
    """
    enabled: bool = Field(
        True,
        description=(
            "Whether this model is eligible for routing and judging. "
            "Disabling a model removes it from consideration without "
            "deleting configuration."
        ),
    )

    provider: ProviderType = Field(
        ...,
        description="LLM provider for this model (must match key type).",
    )

    model_id: str = Field(
        ...,
        description="Provider-specific model identifier.",
    )

    key_instance: str = Field(
        ...,
        description="Key instance used to authenticate requests for this model.",
    )

    pricing: Pricing = Field(
        ...,
        description="Pricing configuration for cost accounting. Mandatory.",
    )

    limits: Limits = Field(
        ...,
        description="Local rate limits enforced by SentinelRouter. Mandatory.",
    )
```

✔ Limits remain **mandatory**
✔ Pricing remains **mandatory**
✔ Operators can now safely disable models

---

# 2️⃣ Exact updated validator code (drop-in replacement)

This is the **complete `validate_sentinel_integrity`**, incorporating all your requests.

```python
@model_validator(mode="after")
def validate_sentinel_integrity(self) -> "SentinelConfig":
    # ------------------------------------------------------------------
    # 1. Validate KeyInstance → Key references
    # ------------------------------------------------------------------
    for ki_id, inst in self.key_instances.items():
        if inst.key_ref not in self.keys:
            raise ValueError(
                f"KeyInstance '{ki_id}' refers to missing key '{inst.key_ref}'"
            )

    # ------------------------------------------------------------------
    # 2. Validate Model → KeyInstance references and provider type safety
    # ------------------------------------------------------------------
    for model_id, model in self.models.items():
        if model.key_instance not in self.key_instances:
            raise ValueError(
                f"Model '{model_id}' refers to missing key_instance '{model.key_instance}'"
            )

        key_ref = self.key_instances[model.key_instance].key_ref
        key_type = self.keys[key_ref].type

        if model.provider != key_type:
            raise ValueError(
                f"Model '{model_id}' provider '{model.provider}' does not match "
                f"key '{key_ref}' provider '{key_type}'"
            )

    # ------------------------------------------------------------------
    # 3. Validate routing tiers are non-empty
    # ------------------------------------------------------------------
    if not self.routing_policy.weak_tier.order:
        raise ValueError("routing_policy.weak_tier.order must not be empty")

    if not self.routing_policy.strong_tier.order:
        raise ValueError("routing_policy.strong_tier.order must not be empty")

    # ------------------------------------------------------------------
    # 4. Validate routing tiers refer to existing, enabled models
    # ------------------------------------------------------------------
    for tier_name, tier in [
        ("weak_tier", self.routing_policy.weak_tier),
        ("strong_tier", self.routing_policy.strong_tier),
    ]:
        for model_id in tier.order:
            if model_id not in self.models:
                raise ValueError(
                    f"routing_policy.{tier_name} refers to missing model '{model_id}'"
                )
            if not self.models[model_id].enabled:
                raise ValueError(
                    f"routing_policy.{tier_name} refers to disabled model '{model_id}'"
                )

    # ------------------------------------------------------------------
    # 5. Prevent overlap between weak and strong tiers
    # ------------------------------------------------------------------
    weak_set = set(self.routing_policy.weak_tier.order)
    strong_set = set(self.routing_policy.strong_tier.order)
    overlap = weak_set & strong_set

    if overlap:
        raise ValueError(
            f"Models cannot appear in both weak and strong tiers: {sorted(overlap)}"
        )

    # ------------------------------------------------------------------
    # 6. Validate Judge configuration
    # ------------------------------------------------------------------
    if self.judge.enabled:
        if not self.judge.model_order:
            raise ValueError(
                "judge.enabled is True but judge.model_order is empty"
            )

        for model_id in self.judge.model_order:
            if model_id not in self.models:
                raise ValueError(
                    f"judge.model_order refers to missing model '{model_id}'"
                )
            if not self.models[model_id].enabled:
                raise ValueError(
                    f"judge.model_order refers to disabled model '{model_id}'"
                )

    # ------------------------------------------------------------------
    # 7. Semantic cache + judge interaction warning
    # ------------------------------------------------------------------
    if self.semantic_cache.enabled and not self.judge.enabled:
        # This is intentionally NOT a hard error.
        # Semantic cache can function without judge, but only if
        # historical routing data already exists.
        import warnings
        warnings.warn(
            "semantic_cache.enabled=True while judge.enabled=False. "
            "Semantic cache will not learn new routing decisions without "
            "an active judge. This is safe but typically unintended.",
            UserWarning,
        )

    return self
```

---

# 3️⃣ Why this validation set is operator-correct

### ✅ Prevents silent footguns

* No ghost keys
* No ghost models
* No disabled models in routing/judge
* No empty tiers
* No ambiguous weak/strong overlap

### ✅ Allows intentional advanced use

* Semantic cache without judge → **warning, not failure**
* Model disabling → safe live-ops
* Multiple keys per model → first-class

### ✅ Errors fail fast and explain *why*

Every `ValueError`:

* names the exact config path
* explains what the operator must fix
* avoids “mystery runtime behavior”

---

# Final assessment (very important)

> **This schema + validator now qualifies as operator-grade.**

It enforces:

* Referential integrity
* Policy clarity
* Safety invariants
* Intentional flexibility

And it does so **without baking in hard-coded behavior**, exactly as you requested.

---

## What this unlocks next (when you’re ready)

* Auto-generated config docs
* Admin UI with confidence (clear editable vs static)
* Safe config reloads
* Interview-ready “explain your config system” story

If you want, next I can:

* generate a **sample fully commented YAML** for users
* or map this schema **1-to-1 to your current runtime objects**
