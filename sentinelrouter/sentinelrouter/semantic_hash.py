"""
Shared helpers for computing semantic hashes (SimHash) for prompts and context.
"""

import hashlib
from typing import List, Optional


def _tokenize(text: str) -> List[str]:
    """Simple whitespace tokenizer used for SimHash computation."""
    return text.lower().split()


def compute_simhash(text: str, hash_bits: int = 64) -> int:
    """
    Compute a SimHash (semantic hash) of the input text.

    Returns an integer of `hash_bits` bits.
    """
    vector = [0] * hash_bits
    tokens = _tokenize(text)
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


def hamming_distance(a: int, b: int, hash_bits: int = 64) -> int:
    """Compute Hamming distance between two integers of `hash_bits` bits."""
    xor = a ^ b
    distance = 0
    while xor:
        distance += xor & 1
        xor >>= 1
    return distance


def semantic_hash_for_payload(prompt: str, context: Optional[str] = None, hash_bits: int = 64) -> int:
    """
    Compute a SimHash for the prompt combined with optional context to ensure
    routing/cache keys incorporate conversation state.
    """
    combined = prompt if context is None else f"{prompt}\n---\n{context}"
    return compute_simhash(combined, hash_bits=hash_bits)
