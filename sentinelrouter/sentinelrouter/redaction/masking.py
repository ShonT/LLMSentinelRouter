"""
Masking strategies for redacted sensitive data.

Provides different approaches to replacing detected sensitive values:
- SimpleMasking: Static replacement (fastest)
- HMACMasking: Deterministic hashing with referential integrity (staff-level)
"""

import hmac
import hashlib
from abc import ABC, abstractmethod


class MaskingStrategy(ABC):
    """Abstract base class for masking strategies."""

    @abstractmethod
    def mask(self, value: str, pattern_name: str = None) -> str:
        """
        Mask a sensitive value.

        Args:
            value: The sensitive value to mask
            pattern_name: Optional name of the pattern that matched

        Returns:
            The masked replacement string
        """
        pass


class SimpleMasking(MaskingStrategy):
    """
    Fastest approach: Static replacement.

    All matches are replaced with the same placeholder.
    Pros: Fast, simple, no configuration needed
    Cons: No way to correlate multiple occurrences of same value
    """

    def __init__(self, placeholder: str = "[REDACTED]"):
        """
        Initialize with custom placeholder.

        Args:
            placeholder: The replacement text (default: [REDACTED])
        """
        self.placeholder = placeholder

    def mask(self, value: str, pattern_name: str = None) -> str:
        """Replace value with static placeholder."""
        if pattern_name:
            return f"[REDACTED:{pattern_name}]"
        return self.placeholder


class HMACMasking(MaskingStrategy):
    """
    Staff-level approach: Deterministic, stateless referential integrity.

    Uses HMAC-SHA256 to create deterministic hashes of sensitive values.
    Same value always produces same hash, enabling correlation while
    maintaining security.

    Pros:
    - Referential integrity: Same secret → same hash
    - Stateless: No database needed
    - Collision-resistant at scale (SHA256)
    - Reversible with salt (for authorized audits)

    Cons:
    - Slightly slower than simple masking
    - Requires secure salt management
    """

    def __init__(self, salt: str, hash_length: int = 10):
        """
        Initialize with HMAC salt.

        Args:
            salt: Secret salt for HMAC (should be unique per deployment)
            hash_length: Number of hex characters to include in output (default: 10)
        """
        self.salt = salt.encode("utf-8")
        self.hash_length = hash_length

    def mask(self, value: str, pattern_name: str = None) -> str:
        """
        Create deterministic HMAC-based redaction.

        Example output: <REDACTED_7a12b9f4c3>
        """
        # Use HMAC-SHA256 for collision resistance at scale
        digest = hmac.new(self.salt, value.encode("utf-8"), hashlib.sha256).hexdigest()

        # Truncate to specified length
        short_hash = digest[: self.hash_length]

        if pattern_name:
            # Include pattern name for better debugging
            safe_name = pattern_name.replace(" ", "_")
            return f"<REDACTED:{safe_name}:{short_hash}>"

        return f"<REDACTED_{short_hash}>"

    def verify(self, value: str, redacted: str) -> bool:
        """
        Verify if a redacted string matches a plaintext value.

        Args:
            value: The plaintext value to check
            redacted: The redacted string to verify against

        Returns:
            True if value produces the given redacted string
        """
        expected = self.mask(value)
        return expected == redacted


class PatternAwareMasking(MaskingStrategy):
    """
    Wraps another strategy but always includes pattern name in output.

    Useful for debugging and audit logs to know what type of
    sensitive data was detected.
    """

    def __init__(self, base_strategy: MaskingStrategy):
        """
        Initialize with a base masking strategy.

        Args:
            base_strategy: The underlying strategy to use for actual masking
        """
        self.base_strategy = base_strategy

    def mask(self, value: str, pattern_name: str = None) -> str:
        """Always include pattern name in masked output."""
        return self.base_strategy.mask(value, pattern_name or "UNKNOWN")
