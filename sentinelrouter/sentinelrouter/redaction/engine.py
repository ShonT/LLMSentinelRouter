"""
RedactionEngine: Core orchestrator for sensitive data protection.

Supports three operational modes:
- NONE: Redaction disabled (passthrough)
- LOGS: Redact in audit logs only, LLM sees original
- STRICT: Redact before LLM processing (LLM sees masked data)
"""

import logging
from enum import Enum
from typing import List, Optional, Dict, Tuple

from .patterns import RedactionPattern, CLOUDS_AND_PII_PATTERNS
from .masking import MaskingStrategy, SimpleMasking, HMACMasking

logger = logging.getLogger(__name__)


class RedactionMode(str, Enum):
    """
    Operational modes for the redaction engine.
    
    NONE: Disabled - no redaction occurs
    LOGS: Redact in audit logs only - LLM sees original prompt
    STRICT: Redact before LLM processing - LLM sees masked values
    """
    NONE = "none"
    LOGS = "logs"
    STRICT = "strict"


class RedactionResult:
    """Result of a redaction operation."""
    
    def __init__(
        self,
        original_text: str,
        redacted_text: str,
        matches: List[Tuple[str, str, int, int]],  # (pattern_name, matched_value, start, end)
        patterns_triggered: Dict[str, int]  # pattern_name -> count
    ):
        self.original_text = original_text
        self.redacted_text = redacted_text
        self.matches = matches
        self.patterns_triggered = patterns_triggered
        self.has_sensitive_data = len(matches) > 0
    
    def __repr__(self):
        return (
            f"RedactionResult(has_sensitive_data={self.has_sensitive_data}, "
            f"patterns_triggered={self.patterns_triggered})"
        )


class RedactionEngine:
    """
    Core engine for detecting and masking sensitive data.
    
    Features:
    - Modular pattern registry
    - Pluggable masking strategies
    - Three operational modes (NONE/LOGS/STRICT)
    - Category-based pattern filtering
    - Performance-optimized matching
    """
    
    def __init__(
        self,
        mode: RedactionMode = RedactionMode.LOGS,
        masking_strategy: Optional[MaskingStrategy] = None,
        patterns: Optional[List[RedactionPattern]] = None,
        enabled_categories: Optional[List[str]] = None
    ):
        """
        Initialize the redaction engine.
        
        Args:
            mode: Operational mode (NONE/LOGS/STRICT)
            masking_strategy: Strategy for masking values (default: SimpleMasking)
            patterns: Custom pattern list (default: CLOUDS_AND_PII_PATTERNS)
            enabled_categories: Filter patterns by category (default: all)
        """
        self.mode = mode
        self.masking_strategy = masking_strategy or SimpleMasking()
        
        # Use provided patterns or default registry
        all_patterns = patterns or CLOUDS_AND_PII_PATTERNS
        
        # Filter by categories if specified
        if enabled_categories:
            from .patterns import PATTERN_CATEGORIES
            enabled_names = set()
            for category in enabled_categories:
                enabled_names.update(PATTERN_CATEGORIES.get(category, []))
            self.patterns = [p for p in all_patterns if p.name in enabled_names]
        else:
            self.patterns = all_patterns
        
        logger.info(
            f"RedactionEngine initialized: mode={mode}, "
            f"patterns={len(self.patterns)}, strategy={type(masking_strategy).__name__}"
        )
    
    def scrub(self, text: str) -> RedactionResult:
        """
        Detect and redact sensitive data in text.
        
        Args:
            text: The text to scan and redact
            
        Returns:
            RedactionResult with original, redacted text, and match metadata
        """
        if not text or self.mode == RedactionMode.NONE:
            # Passthrough mode or empty text
            return RedactionResult(text, text, [], {})
        
        matches: List[Tuple[str, str, int, int]] = []
        patterns_triggered: Dict[str, int] = {}
        
        # Scan for all patterns
        for pattern in self.patterns:
            for match in pattern.regex.finditer(text):
                # Determine what to redact
                if pattern.group_name:
                    # Specific group (e.g., password in connection string)
                    try:
                        matched_value = match.group(pattern.group_name)
                        start, end = match.span(pattern.group_name)
                    except IndexError:
                        # Fallback to full match if group doesn't exist
                        matched_value = match.group(0)
                        start, end = match.span()
                else:
                    # Full match
                    matched_value = match.group(0)
                    start, end = match.span()
                
                matches.append((pattern.name, matched_value, start, end))
                patterns_triggered[pattern.name] = patterns_triggered.get(pattern.name, 0) + 1
        
        # Sort matches by position (descending) to replace from end to start
        # This avoids position shifting issues
        matches.sort(key=lambda m: m[2], reverse=True)
        
        # Apply masking
        redacted_text = text
        for pattern_name, matched_value, start, end in matches:
            replacement = self.masking_strategy.mask(matched_value, pattern_name)
            redacted_text = redacted_text[:start] + replacement + redacted_text[end:]
        
        result = RedactionResult(text, redacted_text, matches, patterns_triggered)
        
        if result.has_sensitive_data:
            logger.warning(
                f"Sensitive data detected: {len(matches)} matches across "
                f"{len(patterns_triggered)} patterns: {list(patterns_triggered.keys())}"
            )
        
        return result
    
    def scrub_dict(self, data: Dict) -> Dict:
        """
        Recursively scrub all string values in a dictionary.
        
        Args:
            data: Dictionary to scrub
            
        Returns:
            New dictionary with redacted values
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.scrub(value).redacted_text
            elif isinstance(value, dict):
                result[key] = self.scrub_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.scrub(item).redacted_text if isinstance(item, str)
                    else self.scrub_dict(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
    
    def should_redact_for_llm(self) -> bool:
        """Check if redaction should be applied before LLM processing."""
        return self.mode == RedactionMode.STRICT
    
    def should_redact_for_logs(self) -> bool:
        """Check if redaction should be applied to audit logs."""
        return self.mode in (RedactionMode.LOGS, RedactionMode.STRICT)
    
    def set_mode(self, mode: RedactionMode):
        """Change operational mode at runtime."""
        old_mode = self.mode
        self.mode = mode
        logger.info(f"RedactionEngine mode changed: {old_mode} → {mode}")
    
    def get_stats(self) -> Dict:
        """Get engine statistics and configuration."""
        return {
            "mode": self.mode.value,
            "patterns_loaded": len(self.patterns),
            "masking_strategy": type(self.masking_strategy).__name__,
            "pattern_names": [p.name for p in self.patterns],
        }
