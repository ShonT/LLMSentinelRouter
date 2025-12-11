"""
Example of how to integrate ModelRegistry into the existing Router.

This shows the minimal changes needed to support backup weak models.
"""

from typing import Dict, Any, Optional
from .model_registry import ModelRegistry, ModelTier, ProviderHealthTracker
from .clients import LLMResponse, LLMClientError

# In Router.__init__, add:
class RouterWithRegistry:
    """
    Enhanced Router with model registry support.
    
    This demonstrates how to integrate the ModelRegistry
    into the existing Router class with minimal changes.
    """
    
    def __init__(self, db_session, model_registry: ModelRegistry):
        # ... existing initialization ...
        self.model_registry = model_registry
        # Remove: self.budget, self.judge, etc. (keep as-is)
    
    async def route_with_failover(
        self,
        session_id: str,
        prompt: str,
        messages: list,
        request_id: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Enhanced routing with automatic failover to backup models.
        
        Changes from original route():
        1. Use model_registry.call_with_failover() instead of direct client calls
        2. Automatically tries backup weak models if primary fails
        3. Returns provider_id instead of just "deepseek"/"anthropic"
        """
        
        # Steps 1-4: Budget, Cycle Detection, Judge, Threshold (UNCHANGED)
        # ... (copy from original route() method) ...
        
        # Determine routing decision (UNCHANGED)
        route_decision = "weak"  # or "strong" based on _decide_route()
        
        # NEW: Map decision to tier
        tier = ModelTier.WEAK if route_decision == "weak" else ModelTier.STRONG
        
        # NEW: Call with automatic failover
        try:
            response, provider_id = await self.model_registry.call_with_failover(
                tier=tier,
                messages=messages,
                max_attempts=3,  # Try up to 3 providers (primary + 2 backups)
            )
            model_used = provider_id
            
        except LLMClientError as e:
            # If all providers in tier failed, try opposite tier as last resort
            logger.error(f"All {tier.value} providers failed: {e}")
            fallback_tier = ModelTier.STRONG if tier == ModelTier.WEAK else ModelTier.WEAK
            logger.info(f"Last resort: trying {fallback_tier.value} tier")
            
            try:
                response, provider_id = await self.model_registry.call_with_failover(
                    tier=fallback_tier,
                    messages=messages,
                    max_attempts=3,
                )
                model_used = provider_id
            except LLMClientError as e:
                raise  # Re-raise if even fallback fails
        
        # Rest of the method (UNCHANGED)
        # - Update cycle detection
        # - Update budget
        # - Log audit
        # - Return result
        
        return {
            "model_used": model_used,  # Now returns provider_id like "deepseek-primary"
            "response": response,
            "complexity_score": 0.5,  # ... from judge
            "impact_scope": "LOW",     # ... from judge
            "reasoning": "...",        # ... decision reason
        }


# Configuration example
def create_model_registry() -> ModelRegistry:
    """
    Factory function to create and configure the model registry.
    
    This shows how to register primary + backup weak models.
    """
    from .clients import DeepSeekClient, AnthropicClient
    from .model_registry import ModelProvider
    
    registry = ModelRegistry()
    
    # Register primary weak model (DeepSeek)
    primary_weak = ModelProvider(
        provider_id="deepseek-primary",
        tier=ModelTier.WEAK,
        client=DeepSeekClient(),
        priority=0,  # Highest priority
        display_name="DeepSeek (Primary)"
    )
    registry.register_provider(primary_weak)
    
    # Register backup weak model #1 (could be another DeepSeek endpoint)
    backup_weak_1 = ModelProvider(
        provider_id="deepseek-backup-1",
        tier=ModelTier.WEAK,
        client=DeepSeekClient(),  # Or different client for backup endpoint
        priority=1,  # Second priority
        display_name="DeepSeek Backup #1"
    )
    registry.register_provider(backup_weak_1)
    
    # Register backup weak model #2 (could be different provider like Groq)
    # backup_weak_2 = ModelProvider(
    #     provider_id="groq-llama-3",
    #     tier=ModelTier.WEAK,
    #     client=GroqClient(),  # Need to implement
    #     priority=2,
    #     display_name="Groq Llama 3 (Backup)"
    # )
    # registry.register_provider(backup_weak_2)
    
    # Register strong model (Anthropic)
    primary_strong = ModelProvider(
        provider_id="anthropic-claude",
        tier=ModelTier.STRONG,
        client=AnthropicClient(),
        priority=0,
        display_name="Claude Opus 4.5"
    )
    registry.register_provider(primary_strong)
    
    return registry


# Usage in server.py
"""
In server.py, modify the route_request function:

# OLD:
async def route_request(...):
    with get_db() as db:
        router = Router(db)
        result = await router.route(...)
        return result

# NEW:
# Global model registry (create once at startup)
_model_registry = None

def get_model_registry() -> ModelRegistry:
    global _model_registry
    if _model_registry is None:
        _model_registry = create_model_registry()
    return _model_registry

async def route_request(...):
    with get_db() as db:
        registry = get_model_registry()
        router = RouterWithRegistry(db, registry)
        result = await router.route_with_failover(...)
        return result
"""
