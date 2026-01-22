Here is the implementation plan to integrate these three modes into SentinelRouter.

1. Environment Configuration

First, update your config.py to support the new REDACTION_LEVEL and the SEMANTIC_STRATEGY toggle.

Python
from enum import Enum

class SemanticStrategy(str, Enum):
    SIMHASH = "SIMHASH"           # Ultra-low RAM, heuristic matching
    VECTORDB_LOCAL = "VECTORDB_LOCAL" # <100MB RAM, local embeddings (Default)
    VECTORDB_API = "VECTORDB_API"   # Gold standard precision, API-based
2. Strategy Implementation Details

Mode A: SIMHASH (The Baseline)

You already have this implemented. To ensure it’s not too brittle, the "Production Fix" is to normalize the input (lowercase, strip whitespace, remove punctuation) before hashing.

Mode B: VECTORDB_LOCAL (The Balanced Default)

To stay under 100MB of RAM, we avoid full-blown deep learning frameworks like PyTorch or TensorFlow. Instead, we use ONNX Runtime with the all-MiniLM-L6-v2 model.

Model: all-MiniLM-L6-v2 (quantized to ONNX format).

Memory Footprint: ~45MB for the model + ~30MB for the ONNX runtime. Total: <80MB.

Performance: ~10-20ms per inference on a standard CPU.

Mode C: VECTORDB_API (The Gold Standard)

This uses external providers (OpenAI's text-embedding-3-small or Anthropic's Voyage) to generate vectors.

Precision: Highest (handles complex paraphrasing).

Cost: ~$0.00002 per request.

Latency: 200ms+ (network dependent).

3. Modular Architecture Plan

We will use the Strategy Pattern to make these interchangeable.

sentinelrouter/semantic/factory.py

Python
class SemanticProcessor(ABC):
    @abstractmethod
    async def get_embedding(self, text: str): pass

class SimHashProcessor(SemanticProcessor):
    # Uses your existing SimHash logic
    ...

class LocalVectorProcessor(SemanticProcessor):
    def __init__(self):
        # Initialize ONNX runtime with MiniLM-L6-v2
        import onnxruntime as ort
        self.session = ort.InferenceSession("models/minilm_v2.onnx")
    ...

class APIVectorProcessor(SemanticProcessor):
    # Calls OpenAI/Anthropic Embedding API
    ...
4. Database Storage: SQLite + LanceDB

Even with different embedding methods, you need to store the results.

For SIMHASH: Continue using your existing SQLite table with the simhash column.

For VECTORDB (Local or API): Use LanceDB (embedded). It stores the vectors on disk and only pulls what it needs into memory during a search.

Memory: LanceDB's memory overhead is negligible (~20-40MB) because it is written in Rust and uses disk-based indexing.

5. Implementation Roadmap

Task	Detail	Memory Usage
Model Quantization	Convert all-MiniLM-L6-v2 to ONNX format to save RAM.	-
Unified Interface	Create SemanticEngine that wraps all 3 methods.	<5 MB
Integration	Update router_logic.py to call the engine before the judge.	-
LanceDB Setup	Initialize local disk-based vector store.	~30 MB
Total Overhead	(Local Vector Mode)	~85-95 MB
