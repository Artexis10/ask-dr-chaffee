#!/usr/bin/env python3
"""
Standalone script to generate embeddings for existing chunks.
Useful for backfilling embeddings or updating to a new model.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.common.database import DatabaseManager
from scripts.common.embeddings import EmbeddingGenerator

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Generate embeddings for all chunks without embeddings"""
    logger.info("Starting embedding generation")
    
    try:
        db = DatabaseManager()
        embedder = EmbeddingGenerator()
        
        # Get chunks without embeddings
        chunks_to_embed = db.get_sources_without_embeddings()
        
        if not chunks_to_embed:
            logger.info("No chunks need embeddings")
            return
        
        logger.info(f"Generating embeddings for {len(chunks_to_embed)} chunks")
        
        # Process in batches
        batch_size = 100
        for i in range(0, len(chunks_to_embed), batch_size):
            batch = chunks_to_embed[i:i + batch_size]
            texts = [chunk['text'] for chunk in batch]
            
            # Generate embeddings
            embeddings = embedder.generate_embeddings(texts)
            
            # Update database
            for chunk, embedding in zip(batch, embeddings):
                db.update_chunk_embedding(chunk['id'], embedding)
            
            batch_num = i//batch_size + 1
            total_batches = (len(chunks_to_embed) + batch_size - 1)//batch_size
            logger.info(f"Processed batch {batch_num}/{total_batches}")
        
        logger.info("Embedding generation completed successfully")
        
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
