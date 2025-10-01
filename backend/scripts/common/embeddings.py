import os
from typing import List, Optional
import logging
import threading

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    """Enhanced embedding generator supporting OpenAI and local models"""
    # Class-level lock for thread safety
    _lock = threading.Lock()
    
    def __init__(self, model_name: str = None, embedding_provider: str = None):
        # Determine embedding provider (openai or local)
        self.provider = embedding_provider or os.getenv('EMBEDDING_PROVIDER', 'openai')
        
        if self.provider == 'openai':
            self.model_name = model_name or os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large')
            self.embedding_dimensions = int(os.getenv('EMBEDDING_DIMENSIONS', '384'))  # Reduced for pgvector compatibility
            self.openai_client = None
        else:
            # Local sentence-transformers - read dimensions from environment
            self.model_name = model_name or os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
            self.embedding_dimensions = int(os.getenv('EMBEDDING_DIMENSIONS', '384'))  # Read from .env
            self.model = None
        
        logger.info(f"Embedding provider: {self.provider}, model: {self.model_name}, dimensions: {self.embedding_dimensions}")
        
    def _load_openai_client(self):
        """Load OpenAI client for embeddings"""
        if self.openai_client is None:
            with EmbeddingGenerator._lock:
                if self.openai_client is None:
                    try:
                        import openai
                        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
                        logger.info("OpenAI client loaded successfully")
                    except ImportError:
                        raise ImportError("OpenAI package not available. Install with: pip install openai")
                    except Exception as e:
                        raise ValueError(f"Failed to initialize OpenAI client: {e}")
        
        return self.openai_client
    
    def _load_local_model(self):
        """Load local SentenceTransformer model"""
        if self.model is None:
            with EmbeddingGenerator._lock:
                if self.model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                        logger.info(f"Loading local embedding model: {self.model_name}")
                        self.model = SentenceTransformer(self.model_name, device="cpu")
                        self.model.eval()
                        logger.info("Local embedding model loaded successfully")
                    except ImportError:
                        raise ImportError("sentence-transformers package not available. Install with: pip install sentence-transformers")
                    except Exception as e:
                        raise ValueError(f"Failed to load local model: {e}")
        
        return self.model
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        if not texts:
            return []
        
        if self.provider == 'openai':
            return self._generate_openai_embeddings(texts)
        else:
            return self._generate_local_embeddings(texts)
    
    def _generate_openai_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API"""
        client = self._load_openai_client()
        
        try:
            # Process in batches to handle API limits
            batch_size = 100  # OpenAI limit
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                logger.debug(f"Generating OpenAI embeddings for batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")
                
                response = client.embeddings.create(
                    model=self.model_name,
                    input=batch_texts,
                    dimensions=self.embedding_dimensions  # Reduce dimensions to match pgvector schema
                )
                
                batch_embeddings = [embedding.embedding for embedding in response.data]
                all_embeddings.extend(batch_embeddings)
            
            logger.info(f"Generated {len(all_embeddings)} OpenAI embeddings")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            # Fallback to local model
            logger.warning("Falling back to local embedding model")
            return self._generate_local_embeddings(texts)
    
    def _generate_local_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local SentenceTransformer model"""
        model = self._load_local_model()
        
        try:
            # Generate embeddings in batches
            embeddings = model.encode(texts, batch_size=32, show_progress_bar=len(texts) > 10)
            
            # Convert to list of lists for JSON serialization
            result = [embedding.tolist() if hasattr(embedding, 'tolist') else embedding for embedding in embeddings]
            logger.info(f"Generated {len(result)} local embeddings")
            return result
            
        except Exception as e:
            logger.error(f"Local embedding generation failed: {e}")
            return []
    
    def generate_single_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text"""
        if not text or not text.strip():
            return None
            
        embeddings = self.generate_embeddings([text])
        return embeddings[0] if embeddings else None
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this generator"""
        return self.embedding_dimensions
