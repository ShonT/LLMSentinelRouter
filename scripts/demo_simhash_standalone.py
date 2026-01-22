#!/usr/bin/env python3
"""
Standalone demonstration of SimHash semantic similarity.

This demonstrates the SIMHASH strategy without requiring full package initialization.
"""

import hashlib
import re


def tokenize(text):
    """Simple whitespace tokenizer."""
    return text.lower().split()


def normalize_text(text):
    """Normalize text before hashing."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[^\w\s\']', '', text)
    return text


def compute_simhash(text, hash_bits=64):
    """Compute SimHash of text."""
    vector = [0] * hash_bits
    tokens = tokenize(normalize_text(text))
    
    if not tokens:
        return 0
    
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        bitmask = int.from_bytes(digest[:8], byteorder="big", signed=False)
        
        for i in range(hash_bits):
            bit = (bitmask >> i) & 1
            vector[i] += 1 if bit else -1
    
    simhash = 0
    for i in range(hash_bits):
        if vector[i] >= 0:
            simhash |= 1 << i
    
    return simhash


def hamming_distance(a, b, hash_bits=64):
    """Compute Hamming distance between two hashes."""
    xor = a ^ b
    distance = 0
    while xor:
        distance += xor & 1
        xor >>= 1
    return distance


def similarity(hash1, hash2, hash_bits=64):
    """Compute normalized similarity (0.0 to 1.0)."""
    distance = hamming_distance(hash1, hash2, hash_bits)
    return 1.0 - (distance / hash_bits)


def main():
    """Run demonstration."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║   SIMHASH SEMANTIC SIMILARITY DEMONSTRATION                    ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    
    print("\n" + "=" * 70)
    print("MODE A: SIMHASH (Baseline - Ultra-fast, Heuristic)")
    print("=" * 70)
    
    test_cases = [
        ("Exact Match", "What is the capital of France?", "What is the capital of France?", True),
        ("Case Insensitive", "HELLO WORLD", "hello world", True),
        ("Near Duplicate", "The quick brown fox jumps", "The fast brown fox jumps", True),
        ("Paraphrase", "What is AI?", "Can you explain artificial intelligence?", False),
        ("Different", "What is AI?", "How to cook pasta?", False),
    ]
    
    print(f"\n{'Test':20} {'Text 1':30} {'Text 2':30} {'Similarity':12} {'Result':10}")
    print("-" * 112)
    
    for test_name, text1, text2, expected in test_cases:
        hash1 = compute_simhash(text1)
        hash2 = compute_simhash(text2)
        sim = similarity(hash1, hash2)
        is_similar = sim >= 0.85
        
        result = "✅ MATCH" if is_similar else "❌ NO MATCH"
        expected_str = "(expected)" if is_similar == expected else "(UNEXPECTED)"
        
        print(f"{test_name:20} {text1[:28]:30} {text2[:28]:30} {sim:>11.3f} {result:10} {expected_str}")
    
    print("\n" + "=" * 70)
    print("PERFORMANCE CHARACTERISTICS")
    print("=" * 70)
    print("\n✅ Strengths:")
    print("  • Ultra-fast: <1ms per operation")
    print("  • Memory efficient: ~5KB")
    print("  • No dependencies")
    print("  • Excellent for exact/near duplicates")
    print("  • Case insensitive")
    print("  • Whitespace normalized")
    
    print("\n⚠️  Limitations:")
    print("  • Poor paraphrase detection (by design)")
    print("  • Word order sensitive")
    print("  • Synonym-blind")
    
    print("\n" + "=" * 70)
    print("ALTERNATIVE STRATEGIES")
    print("=" * 70)
    print("\nFor better paraphrase detection, use:")
    
    print("\n📊 VECTORDB_LOCAL (Recommended)")
    print("  • Memory: ~80MB")
    print("  • Latency: 10-20ms")
    print("  • Detects paraphrases: ✅")
    print("  • Dependencies: onnxruntime, transformers")
    print("  • Command: pip install onnxruntime transformers")
    
    print("\n🌐 VECTORDB_API (Highest Precision)")
    print("  • Memory: ~5MB")
    print("  • Latency: 200ms+")
    print("  • Detects paraphrases: ✅✅")
    print("  • Cost: ~$0.00002 per request")
    print("  • Requires: API key (OPENAI_API_KEY)")
    
    print("\n" + "=" * 70)
    print("CONFIGURATION")
    print("=" * 70)
    print("\nAdd to .env:")
    print("\n# Use SimHash (current, no dependencies)")
    print("SEMANTIC_STRATEGY=SIMHASH")
    print("SEMANTIC_SIMILARITY_THRESHOLD=0.85")
    
    print("\n# Use Local Vectors (better paraphrase detection)")
    print("SEMANTIC_STRATEGY=VECTORDB_LOCAL")
    print("SEMANTIC_SIMILARITY_THRESHOLD=0.85")
    
    print("\n# Use API Vectors (best accuracy)")
    print("SEMANTIC_STRATEGY=VECTORDB_API")
    print("SEMANTIC_API_KEY=sk-...")
    print("SEMANTIC_SIMILARITY_THRESHOLD=0.85")
    
    print("\n" + "=" * 70)
    print("USAGE IN CODE")
    print("=" * 70)
    print("""
from sentinelrouter.sentinelrouter.enhanced_cycle_detector import EnhancedCycleDetector

# Automatically uses strategy from environment
detector = EnhancedCycleDetector(
    session_id="user123",
    similarity_threshold=0.85
)

# Check for cycles
if await detector.detect_cycle_with_prompt(prompt):
    # Escalate to strong model
    pass
""")
    
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
