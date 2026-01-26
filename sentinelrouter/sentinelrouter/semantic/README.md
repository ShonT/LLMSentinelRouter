# Semantic Processing Module

Three-tiered semantic similarity detection for cycle detection and caching.

## Strategies

### Mode A: SIMHASH (Baseline)
- **Memory**: ~5MB
- **Latency**: <1ms per operation
- **Precision**: Good for exact/near duplicates
- **Dependencies**: None (built-in)

```python
from sentinelrouter.sentinelrouter.semantic import SemanticProcessorFactory, SemanticStrategy

processor = SemanticProcessorFactory.create(SemanticStrategy.SIMHASH)
is_similar = await processor.is_similar(text1, text2, threshold=0.85)
```

### Mode B: VECTORDB_LOCAL (Default)
- **Memory**: ~80MB (45MB model + 30MB runtime + overhead)
- **Latency**: 10-20ms per embedding
- **Precision**: Good (handles paraphrasing)
- **Dependencies**: `onnxruntime`, `transformers`

```python
processor = SemanticProcessorFactory.create(
    SemanticStrategy.VECTORDB_LOCAL,
    similarity_threshold=0.90
)
```

### Mode C: VECTORDB_API (Gold Standard)
- **Memory**: ~5MB
- **Latency**: 200ms+ (network dependent)
- **Precision**: Highest
- **Cost**: ~$0.00002 per request
- **Dependencies**: API key (OpenAI or Voyage AI)

```python
processor = SemanticProcessorFactory.create(
    SemanticStrategy.VECTORDB_API,
    api_key="sk-...",
    provider="openai"
)
```

## Configuration

Add to `.env`:

```bash
# Semantic similarity strategy
SEMANTIC_STRATEGY=VECTORDB_LOCAL  # or SIMHASH, VECTORDB_API
SEMANTIC_SIMILARITY_THRESHOLD=0.85

# For SIMHASH strategy
SEMANTIC_HASH_BITS=64

# For VECTORDB_LOCAL strategy
SEMANTIC_MODEL_PATH=  # Optional custom ONNX model path

# For VECTORDB_API strategy
SEMANTIC_API_KEY=sk-...
SEMANTIC_API_PROVIDER=openai  # or voyage
SEMANTIC_API_MODEL=text-embedding-3-small
```

## Integration with Cycle Detector

Use `EnhancedCycleDetector` instead of `CycleDetector`:

```python
from sentinelrouter.sentinelrouter.enhanced_cycle_detector import EnhancedCycleDetector

detector = EnhancedCycleDetector(
    session_id="user123",
    similarity_threshold=0.85,
    enable_storage=True  # Optional: persist vectors with LanceDB
)

# Add successful requests
cycle_detected = await detector.add_request_response(prompt, response)

# Check for cycles before routing
if await detector.detect_cycle_with_prompt(prompt):
    # Escalate to strong model
    pass
```

## Installation

### Basic (SimHash only)
```bash
# No additional dependencies needed
```

### With Local Vectors
```bash
pip install onnxruntime transformers optimum[onnxruntime]
```

### With Vector Storage
```bash
pip install lancedb pyarrow
```

### With API Embeddings
```bash
# No additional dependencies (uses httpx)
# Just need API key in environment
```

## Performance Comparison

| Strategy | Memory | Latency | Exact Match | Paraphrase | Cost |
|----------|--------|---------|-------------|------------|------|
| SIMHASH | 5MB | <1ms | ✅ Excellent | ⚠️ Limited | Free |
| VECTORDB_LOCAL | 80MB | 10-20ms | ✅ Excellent | ✅ Good | Free |
| VECTORDB_API | 5MB | 200ms+ | ✅ Excellent | ✅✅ Excellent | $0.00002/req |

## Memory Footprint

```python
# Check memory usage
processor = SemanticProcessorFactory.create(strategy)
print(f"Memory: {processor.get_memory_usage_mb():.1f} MB")
```

## Examples

### Detect Exact Duplicates (SimHash)
```python
processor = SemanticProcessorFactory.create(SemanticStrategy.SIMHASH)

text1 = "What is the capital of France?"
text2 = "What is the capital of France?"

assert await processor.is_similar(text1, text2) == True
```

### Detect Paraphrases (Local Vectors)
```python
processor = SemanticProcessorFactory.create(SemanticStrategy.VECTORDB_LOCAL)

text1 = "What is the capital of France?"
text2 = "Can you tell me France's capital city?"

# SimHash would miss this, but vectors detect it
similarity = await processor.is_similar(text1, text2)
print(f"Similarity: {similarity}")  # ~0.88
```

### Search Similar Prompts
```python
from sentinelrouter.sentinelrouter.semantic.vector_store import VectorStore

store = VectorStore(storage_path="data/vectors", use_lancedb=True)

# Store embeddings
embedding = await processor.get_embedding("What is AI?")
await store.add_embedding("session123", "What is AI?", embedding)

# Search
results = await store.search_similar(
    embedding=query_embedding,
    session_id="session123",
    top_k=5,
    similarity_threshold=0.85
)

for text, score, metadata in results:
    print(f"{score:.3f}: {text}")
```

## Factory Pattern

Use `SemanticProcessorFactory.from_settings()` to automatically configure from environment:

```python
from sentinelrouter.sentinelrouter.semantic import SemanticProcessorFactory
from sentinelrouter.sentinelrouter.config import get_settings

settings = get_settings()
processor = SemanticProcessorFactory.from_settings(settings)

# Automatically selects strategy based on SEMANTIC_STRATEGY env var
```

## Architecture

```
┌─────────────────────────────────────────────┐
│         Semantic Processing                 │
├─────────────────────────────────────────────┤
│  Factory                                    │
│  ├── SIMHASH                                │
│  │   └── SimHashProcessor                  │
│  │       • compute_simhash()               │
│  │       • hamming_distance()              │
│  ├── VECTORDB_LOCAL                         │
│  │   └── LocalVectorProcessor              │
│  │       • ONNX Runtime                    │
│  │       • all-MiniLM-L6-v2                │
│  │       • Cosine similarity               │
│  └── VECTORDB_API                           │
│      └── APIVectorProcessor                 │
│          • OpenAI/Voyage API                │
│          • text-embedding-3-small           │
│          • REST client                      │
├─────────────────────────────────────────────┤
│  Storage (Optional)                         │
│  └── VectorStore                            │
│      ├── LanceDB (for vectors)              │
│      └── SQLite (for hashes)                │
└─────────────────────────────────────────────┘
```

## Backward Compatibility

The original `CycleDetector` continues to work with SimHash. Use `EnhancedCycleDetector` for new strategies:

```python
# Old way (still works)
from sentinelrouter.sentinelrouter.cycle_detector import CycleDetector
detector = CycleDetector(session_id="user123")

# New way (recommended)
from sentinelrouter.sentinelrouter.enhanced_cycle_detector import EnhancedCycleDetector
detector = EnhancedCycleDetector(session_id="user123")
```

## Troubleshooting

### "No module named 'onnxruntime'"
```bash
pip install onnxruntime
```

### "No module named 'transformers'"
```bash
pip install transformers
```

### "Model download failed"
Set custom model path or pre-download:
```python
from optimum.onnxruntime import ORTModelForFeatureExtraction

model = ORTModelForFeatureExtraction.from_pretrained(
    'sentence-transformers/all-MiniLM-L6-v2',
    export=True
)
model.save_pretrained('data/models/')
```

### "lancedb not available"
```bash
pip install lancedb pyarrow
```

Vector storage is optional - system works without it using in-memory tracking.
