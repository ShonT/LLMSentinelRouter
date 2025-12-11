"""
Model Registry & Provider Management System

Implements:
- Model registry with primary/backup providers
- Failure tracking with circuit breaker
- Automatic failover to backup models
- Provider health monitoring
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

from .clients import BaseLLMClient, LLMResponse, LLMClientError

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Model tier classification."""
    WEAK = "weak"
    STRONG = "strong"


@dataclass
class ProviderHealth:
    """Track health status of a provider."""
    provider_id: str
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    circuit_open_until: Optional[datetime] = None
    recent_failures: List[datetime] = field(default_factory=list)
    
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open (provider unavailable)."""
        if self.circuit_open_until is None:
            return False
        return datetime.utcnow() < self.circuit_open_until
    
    def get_recent_failure_count(self, window_seconds: int = 300) -> int:
        """Get failure count in recent time window."""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        return sum(1 for failure_time in self.recent_failures if failure_time > cutoff)


@dataclass
class ModelProvider:
    """Represents a model provider with its client and metadata."""
    provider_id: str  # e.g., "deepseek-primary", "deepseek-backup", "anthropic"
    tier: ModelTier
    client: BaseLLMClient
    priority: int = 0  # 0=primary, 1=first backup, 2=second backup, etc.
    display_name: str = ""
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.provider_id
    
    async def chat_completion(self, messages: List[Dict]) -> LLMResponse:
        """Delegate to underlying client."""
        return await self.client.chat_completion(messages)
    
    @property
    def cost_per_token(self) -> float:
        """Get cost per token from client."""
        return self.client.price_per_token


class ProviderHealthTracker:
    """
    Tracks provider health and implements circuit breaker pattern.
    
    Circuit breaker opens after N consecutive failures, preventing
    requests to failing providers for a cooldown period.
    """
    
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._health: Dict[str, ProviderHealth] = {}
    
    def _get_health(self, provider_id: str) -> ProviderHealth:
        """Get or create health record for provider."""
        if provider_id not in self._health:
            self._health[provider_id] = ProviderHealth(provider_id=provider_id)
        return self._health[provider_id]
    
    def record_failure(self, provider_id: str) -> None:
        """Record a failure for a provider."""
        health = self._get_health(provider_id)
        now = datetime.utcnow()
        
        health.failure_count += 1
        health.last_failure = now
        health.recent_failures.append(now)
        
        # Prune old failures (keep last 1 hour)
        cutoff = now - timedelta(hours=1)
        health.recent_failures = [f for f in health.recent_failures if f > cutoff]
        
        # Open circuit breaker if threshold exceeded
        recent_count = health.get_recent_failure_count(window_seconds=300)
        if recent_count >= self.failure_threshold:
            health.circuit_open_until = now + timedelta(seconds=self.cooldown_seconds)
            logger.warning(
                f"Circuit breaker OPEN for {provider_id}: "
                f"{recent_count} failures in last 5 minutes. "
                f"Cooldown until {health.circuit_open_until}"
            )
    
    def record_success(self, provider_id: str) -> None:
        """Record a successful call, resetting failure tracking."""
        health = self._get_health(provider_id)
        health.last_success = datetime.utcnow()
        health.failure_count = 0
        health.recent_failures.clear()
        health.circuit_open_until = None
        logger.debug(f"Provider {provider_id} success, circuit reset")
    
    def is_available(self, provider_id: str) -> bool:
        """Check if provider is available (circuit not open)."""
        health = self._get_health(provider_id)
        
        if health.is_circuit_open():
            logger.debug(f"Provider {provider_id} unavailable: circuit breaker open")
            return False
        
        return True
    
    def get_status(self, provider_id: str) -> Dict:
        """Get detailed status for a provider."""
        health = self._get_health(provider_id)
        return {
            "provider_id": provider_id,
            "available": self.is_available(provider_id),
            "circuit_open": health.is_circuit_open(),
            "failure_count": health.failure_count,
            "recent_failures": health.get_recent_failure_count(),
            "last_failure": health.last_failure,
            "last_success": health.last_success,
        }


class ModelRegistry:
    """
    Central registry for all model providers with failover support.
    
    Features:
    - Register multiple providers per tier (weak/strong)
    - Priority-based selection (primary, backup1, backup2, etc.)
    - Automatic failover when providers fail
    - Circuit breaker pattern to avoid cascading failures
    - Health monitoring and reporting
    """
    
    def __init__(self, health_tracker: Optional[ProviderHealthTracker] = None):
        self._providers: Dict[ModelTier, List[ModelProvider]] = {
            ModelTier.WEAK: [],
            ModelTier.STRONG: [],
        }
        self.health_tracker = health_tracker or ProviderHealthTracker()
    
    def register_provider(self, provider: ModelProvider) -> None:
        """Register a model provider."""
        tier_list = self._providers[provider.tier]
        tier_list.append(provider)
        # Sort by priority (0 = highest priority)
        tier_list.sort(key=lambda p: p.priority)
        logger.info(
            f"Registered {provider.tier.value} model: {provider.provider_id} "
            f"(priority {provider.priority})"
        )
    
    def get_available_providers(
        self, 
        tier: ModelTier, 
        exclude: Optional[List[str]] = None
    ) -> List[ModelProvider]:
        """
        Get list of available providers for a tier, excluding specified ones.
        
        Returns providers in priority order, filtering out:
        - Providers with open circuit breakers
        - Explicitly excluded providers
        """
        exclude = exclude or []
        providers = self._providers[tier]
        
        available = [
            p for p in providers
            if p.provider_id not in exclude
            and self.health_tracker.is_available(p.provider_id)
        ]
        
        return available
    
    def select_provider(
        self, 
        tier: ModelTier, 
        exclude: Optional[List[str]] = None
    ) -> Optional[ModelProvider]:
        """
        Select the next available provider for a tier.
        
        Returns highest priority provider that is:
        - Not in exclude list
        - Has circuit breaker closed
        
        Returns None if no providers available.
        """
        available = self.get_available_providers(tier, exclude)
        
        if not available:
            logger.error(
                f"No available {tier.value} providers! "
                f"Excluded: {exclude}, All: {[p.provider_id for p in self._providers[tier]]}"
            )
            return None
        
        selected = available[0]  # Highest priority
        logger.debug(f"Selected {tier.value} provider: {selected.provider_id}")
        return selected
    
    async def call_with_failover(
        self,
        tier: ModelTier,
        messages: List[Dict],
        max_attempts: int = 3,
    ) -> Tuple[LLMResponse, str]:
        """
        Make LLM call with automatic failover to backup providers.
        
        Args:
            tier: Model tier (weak or strong)
            messages: Chat messages
            max_attempts: Maximum number of providers to try
        
        Returns:
            Tuple of (LLMResponse, provider_id used)
        
        Raises:
            LLMClientError: If all providers fail
        """
        attempted_providers = []
        last_error = None
        
        for attempt in range(max_attempts):
            provider = self.select_provider(tier, exclude=attempted_providers)
            
            if provider is None:
                break  # No more providers to try
            
            attempted_providers.append(provider.provider_id)
            
            try:
                logger.info(
                    f"Attempt {attempt + 1}/{max_attempts}: "
                    f"Calling {provider.display_name} ({provider.provider_id})"
                )
                
                response = await provider.chat_completion(messages)
                
                # Success! Record it and return
                self.health_tracker.record_success(provider.provider_id)
                logger.info(
                    f"✅ Success with {provider.provider_id} "
                    f"(cost: ${response.cost:.6f})"
                )
                return response, provider.provider_id
                
            except LLMClientError as e:
                last_error = e
                logger.error(
                    f"❌ {provider.provider_id} failed: {e}. "
                    f"Trying next backup..."
                )
                self.health_tracker.record_failure(provider.provider_id)
                
                # Continue to next provider
                continue
        
        # All providers failed
        error_msg = (
            f"All {tier.value} providers failed after {len(attempted_providers)} attempts. "
            f"Tried: {attempted_providers}"
        )
        logger.error(error_msg)
        raise LLMClientError(error_msg) from last_error
    
    def get_registry_status(self) -> Dict:
        """Get complete status of all providers."""
        status = {}
        for tier in ModelTier:
            status[tier.value] = [
                {
                    "provider_id": p.provider_id,
                    "display_name": p.display_name,
                    "priority": p.priority,
                    "cost_per_token": p.cost_per_token,
                    **self.health_tracker.get_status(p.provider_id)
                }
                for p in self._providers[tier]
            ]
        return status
