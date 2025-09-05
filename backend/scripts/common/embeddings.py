import os
from typing import List
from sentence_transformers import SentenceTransformer
import logging
import threading

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    # Class-level lock for thread safety
    _lock = threading.Lock()
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
        self.model = None
        
    def load_model(self):
        """Lazy load the embedding model with thread safety"""
        if self.model is None:
            # Use a lock to prevent multiple threads from loading the model simultaneously
            with EmbeddingGenerator._lock:
                # Double-check pattern to avoid unnecessary lock acquisition
                if self.model is None:
                    logger.info(f"Loading embedding model: {self.model_name}")
                    # Explicitly specify device and ensure proper initialization
                    self.model = SentenceTransformer(self.model_name, device="cpu")
                    # Force model to initialize properly
                    self.model.eval()
                    logger.info("Embedding model loaded successfully")
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        self.load_model()
        
        if not texts:
            return []
            
        # Generate embeddings in batches
        embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=True)
        
        # Convert to list of lists for JSON serialization
        return [embedding.tolist() if hasattr(embedding, 'tolist') else embedding for embedding in embeddings]
    
    def generate_single_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        embeddings = self.generate_embeddings([text])
        return embeddings[0] if embeddings else []
