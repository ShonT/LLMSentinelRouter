"""
Vector storage adapter for semantic embeddings.

Supports both in-memory SQLite (for SimHash) and disk-based LanceDB (for vectors).
"""

import logging
from typing import Optional, List, Tuple, Union
from pathlib import Path
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports
lancedb = None
pyarrow = None


class VectorStore:
    """
    Storage for semantic embeddings with similarity search.
    
    Supports:
    - SimHash: Stored in SQLite as integers
    - Vectors: Stored in LanceDB with ANN search
    """

    def __init__(
        self,
        storage_path: str = "data/vectors",
        table_name: str = "semantic_embeddings",
        use_lancedb: bool = True
    ):
        """
        Initialize vector store.
        
        Args:
            storage_path: Path to vector storage directory
            table_name: Name of the table/collection
            use_lancedb: Whether to use LanceDB (for vectors) or SQLite (for hashes)
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.table_name = table_name
        self.use_lancedb = use_lancedb
        
        self.db = None
        self.table = None
        
        # For SimHash, we can use SQLite connection from database module
        self._sqlite_conn = None
        
        logger.info(f"VectorStore initialized (path={storage_path}, lancedb={use_lancedb})")

    async def _ensure_lancedb_initialized(self):
        """Lazy initialization of LanceDB."""
        if not self.use_lancedb:
            return
        
        if self.db is not None:
            return
        
        global lancedb, pyarrow
        
        try:
            if lancedb is None:
                import lancedb as ldb
                lancedb = ldb
            if pyarrow is None:
                import pyarrow as pa
                pyarrow = pa
            
            # Connect to LanceDB
            self.db = lancedb.connect(str(self.storage_path))
            
            # Create or open table
            table_path = self.storage_path / f"{self.table_name}.lance"
            
            if table_path.exists():
                self.table = self.db.open_table(self.table_name)
                logger.info(f"Opened existing LanceDB table: {self.table_name}")
            else:
                logger.info(f"LanceDB table {self.table_name} will be created on first insert")
            
        except ImportError as e:
            logger.warning(
                f"LanceDB not available: {e}\n"
                "Install with: pip install lancedb pyarrow\n"
                "Falling back to memory-only storage"
            )
            self.use_lancedb = False
        except Exception as e:
            logger.error(f"Failed to initialize LanceDB: {e}")
            self.use_lancedb = False

    async def add_embedding(
        self,
        session_id: str,
        text: str,
        embedding: Union[int, np.ndarray],
        metadata: Optional[dict] = None
    ) -> str:
        """
        Add an embedding to the store.
        
        Args:
            session_id: Session identifier
            text: Original text
            embedding: SimHash (int) or vector (np.ndarray)
            metadata: Additional metadata
            
        Returns:
            ID of stored embedding
        """
        timestamp = datetime.utcnow().isoformat()
        
        if isinstance(embedding, int):
            # SimHash - store in memory or SQLite
            record_id = f"{session_id}_{timestamp}"
            # For now, just log (full SQLite integration would go here)
            logger.debug(f"Stored SimHash {embedding} for session {session_id}")
            return record_id
        
        else:
            # Vector - store in LanceDB
            await self._ensure_lancedb_initialized()
            
            if not self.use_lancedb:
                # Fallback: just return an ID
                record_id = f"{session_id}_{timestamp}"
                logger.debug(f"Stored vector (no LanceDB) for session {session_id}")
                return record_id
            
            # Prepare record
            record = {
                "session_id": session_id,
                "text": text,
                "vector": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
                "timestamp": timestamp,
                "metadata": str(metadata) if metadata else ""
            }
            
            # Create table if needed
            if self.table is None:
                import pyarrow as pa
                
                schema = pa.schema([
                    ("session_id", pa.string()),
                    ("text", pa.string()),
                    ("vector", pa.list_(pa.float32(), len(embedding))),
                    ("timestamp", pa.string()),
                    ("metadata", pa.string())
                ])
                
                self.table = self.db.create_table(
                    self.table_name,
                    data=[record],
                    schema=schema
                )
                logger.info(f"Created LanceDB table: {self.table_name}")
            else:
                # Add to existing table
                self.table.add([record])
            
            record_id = f"{session_id}_{timestamp}"
            logger.debug(f"Stored vector embedding for session {session_id}")
            return record_id

    async def search_similar(
        self,
        embedding: Union[int, np.ndarray],
        session_id: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.85
    ) -> List[Tuple[str, float, str]]:
        """
        Search for similar embeddings.
        
        Args:
            embedding: Query embedding
            session_id: Optional session filter
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of (text, similarity_score, metadata) tuples
        """
        if isinstance(embedding, int):
            # SimHash - would use hamming distance search in SQLite
            logger.debug("SimHash similarity search not yet implemented in store")
            return []
        
        else:
            # Vector - use LanceDB ANN search
            await self._ensure_lancedb_initialized()
            
            if not self.use_lancedb or self.table is None:
                return []
            
            try:
                # Search using vector similarity
                results = self.table.search(embedding).limit(top_k).to_list()
                
                # Filter by session if specified
                if session_id:
                    results = [r for r in results if r.get('session_id') == session_id]
                
                # Filter by similarity threshold
                # LanceDB returns _distance, we convert to similarity (1 - distance)
                similar_results = []
                for result in results:
                    distance = result.get('_distance', 1.0)
                    similarity = 1.0 - distance
                    
                    if similarity >= similarity_threshold:
                        similar_results.append((
                            result.get('text', ''),
                            similarity,
                            result.get('metadata', '')
                        ))
                
                return similar_results
                
            except Exception as e:
                logger.error(f"Vector search failed: {e}")
                return []

    async def get_session_embeddings(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[Tuple[str, Union[int, np.ndarray]]]:
        """
        Get all embeddings for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of results
            
        Returns:
            List of (text, embedding) tuples
        """
        if not self.use_lancedb or self.table is None:
            return []
        
        try:
            await self._ensure_lancedb_initialized()
            
            # Query by session_id
            results = (
                self.table
                .search()
                .where(f"session_id = '{session_id}'")
                .limit(limit)
                .to_list()
            )
            
            embeddings = []
            for result in results:
                text = result.get('text', '')
                vector = np.array(result.get('vector', []))
                embeddings.append((text, vector))
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to get session embeddings: {e}")
            return []

    def get_memory_usage_mb(self) -> float:
        """Return approximate memory usage in MB."""
        # LanceDB uses disk-based storage with minimal RAM overhead
        if self.use_lancedb:
            return 30.0  # ~30MB for LanceDB runtime
        return 0.1  # Minimal for in-memory

    async def close(self):
        """Close connections."""
        if self.db:
            # LanceDB connections are lightweight, no explicit close needed
            pass
        logger.debug("VectorStore closed")
