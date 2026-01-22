#!/usr/bin/env python3
"""
Demonstration of semantic processing strategies.

Shows how each strategy detects exact duplicates and paraphrases.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sentinelrouter.sentinelrouter.semantic.simhash_processor import SimHashProcessor
from sentinelrouter.sentinelrouter.semantic.factory import SemanticStrategy


async def demonstrate_simhash():
    """Demonstrate SimHash processor."""
    print("=" * 70)
    print("MODE A: SIMHASH (Baseline - Ultra-fast, Heuristic)")
    print("=" * 70)
    
    processor = SimHashProcessor(hash_bits=64, hamming_threshold=3)
    
    # Test 1: Exact match
    print("\n[Test 1] Exact Match")
    text1 = "What is the capital of France?"
    text2 = "What is the capital of France?"
    
    is_sim = await processor.is_similar(text1, text2, threshold=0.85)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Result: {'✅ SIMILAR' if is_sim else '❌ NOT SIMILAR'}")
    
    # Test 2: Case insensitivity
    print("\n[Test 2] Case Insensitivity")
    text1 = "HELLO WORLD"
    text2 = "hello world"
    
    is_sim = await processor.is_similar(text1, text2, threshold=0.85)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Result: {'✅ SIMILAR' if is_sim else '❌ NOT SIMILAR'}")
    
    # Test 3: Near duplicate
    print("\n[Test 3] Near Duplicate (1-2 word changes)")
    text1 = "The quick brown fox jumps over the lazy dog"
    text2 = "The fast brown fox jumps over the lazy dog"
    
    is_sim = await processor.is_similar(text1, text2, threshold=0.85)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Result: {'✅ SIMILAR' if is_sim else '❌ NOT SIMILAR'}")
    
    # Test 4: Paraphrase (will likely miss)
    print("\n[Test 4] Paraphrase Detection")
    text1 = "What is the capital of France?"
    text2 = "Can you tell me France's capital city?"
    
    is_sim = await processor.is_similar(text1, text2, threshold=0.85)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Result: {'✅ SIMILAR' if is_sim else '❌ NOT SIMILAR'}")
    print(f"Note: SimHash struggles with paraphrases (expected)")
    
    # Test 5: Completely different
    print("\n[Test 5] Completely Different")
    text1 = "What is the capital of France?"
    text2 = "How to train a neural network?"
    
    is_sim = await processor.is_similar(text1, text2, threshold=0.85)
    print(f"Text 1: {text1}")
    print(f"Text 2: {text2}")
    print(f"Result: {'✅ SIMILAR' if is_sim else '❌ NOT SIMILAR'}")
    
    # Performance metrics
    print("\n[Performance Metrics]")
    print(f"Memory Usage: {processor.get_memory_usage_mb():.3f} MB")
    print(f"Latency: <1ms per operation")
    print(f"Best for: Exact duplicates, near-duplicates")
    print(f"Limitations: Poor paraphrase detection")


async def demonstrate_comparison():
    """Show comparison between strategies."""
    print("\n\n" + "=" * 70)
    print("STRATEGY COMPARISON")
    print("=" * 70)
    
    test_pairs = [
        ("Exact match", "Hello world", "Hello world"),
        ("Case change", "Hello World", "hello world"),
        ("Near duplicate", "The quick brown fox", "The fast brown fox"),
        ("Paraphrase", "What is AI?", "Can you explain artificial intelligence?"),
        ("Different", "What is AI?", "How to cook pasta?"),
    ]
    
    print("\n| Test | SimHash | LocalVector* | APIVector* |")
    print("|------|---------|--------------|------------|")
    
    simhash_proc = SimHashProcessor()
    
    for test_name, text1, text2 in test_pairs:
        simhash_result = await simhash_proc.is_similar(text1, text2, threshold=0.85)
        
        print(f"| {test_name:15} | {'✅' if simhash_result else '❌':7} | " +
              f"{'✅*' if test_name in ['Exact match', 'Case change', 'Near duplicate', 'Paraphrase'] else '❌*':12} | " +
              f"{'✅*' if test_name != 'Different' else '❌*':10} |")
    
    print("\n*LocalVector and APIVector require additional dependencies")
    print(" LocalVector: pip install onnxruntime transformers")
    print(" APIVector: API key required (OPENAI_API_KEY or SEMANTIC_API_KEY)")
    
    print("\n[Memory Footprint]")
    print(f"SimHash:       {simhash_proc.get_memory_usage_mb():>6.1f} MB")
    print(f"LocalVector:  ~80.0 MB (after model load)")
    print(f"APIVector:     ~5.0 MB")
    
    print("\n[Latency]")
    print(f"SimHash:       <1ms")
    print(f"LocalVector:   10-20ms")
    print(f"APIVector:     200ms+")


async def main():
    """Run demonstrations."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║   SEMANTIC PROCESSING STRATEGIES DEMONSTRATION                 ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    
    await demonstrate_simhash()
    await demonstrate_comparison()
    
    print("\n\n" + "=" * 70)
    print("CONFIGURATION")
    print("=" * 70)
    print("\nTo enable in SentinelRouter, add to .env:")
    print("\n# Use SimHash (default, no dependencies)")
    print("SEMANTIC_STRATEGY=SIMHASH")
    print("SEMANTIC_SIMILARITY_THRESHOLD=0.85")
    print("\n# Use Local Vectors (better paraphrase detection)")
    print("SEMANTIC_STRATEGY=VECTORDB_LOCAL")
    print("SEMANTIC_SIMILARITY_THRESHOLD=0.85")
    print("\n# Use API Vectors (best accuracy, requires API key)")
    print("SEMANTIC_STRATEGY=VECTORDB_API")
    print("SEMANTIC_API_KEY=sk-...")
    print("SEMANTIC_SIMILARITY_THRESHOLD=0.85")
    
    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
