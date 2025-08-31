"""
Cross-encoder reranker for improving search result quality.
Uses ms-marco-MiniLM model to rerank top vector search results.
"""
import os
from typing import List, Tuple, Dict, Any
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch


class CrossEncoderReranker:
    """Cross-encoder reranker using ms-marco-MiniLM-L-6-v2"""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
    def _load_model(self):
        """Lazy load the model and tokenizer"""
        if self.tokenizer is None:
            print(f"Loading reranker model: {self.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
    
    def rerank(self, query: str, results: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Rerank search results using cross-encoder.
        
        Args:
            query: Search query string
            results: List of search result dictionaries with 'text' field
            top_k: Number of top results to return
            
        Returns:
            Reranked list of results with updated similarity scores
        """
        if not results:
            return results
            
        # Check if reranking is enabled
        if not os.getenv('RERANK_ENABLED', 'false').lower() == 'true':
            return results[:top_k]
            
        self._load_model()
        
        # Prepare input pairs
        pairs = [(query, result['text']) for result in results]
        
        # Tokenize and score
        scores = []
        with torch.no_grad():
            for query_text, doc_text in pairs:
                # Truncate to avoid token limit issues
                inputs = self.tokenizer(
                    query_text, 
                    doc_text, 
                    truncation=True, 
                    max_length=512, 
                    return_tensors="pt"
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                
                outputs = self.model(**inputs)
                score = torch.sigmoid(outputs.logits).cpu().numpy()[0][0]
                scores.append(float(score))
        
        # Combine results with scores and sort
        scored_results = []
        for result, score in zip(results, scores):
            result_copy = result.copy()
            result_copy['rerank_score'] = score
            result_copy['similarity'] = f"{score * 100:.1f}"  # Convert to percentage string
            scored_results.append(result_copy)
        
        # Sort by rerank score descending
        scored_results.sort(key=lambda x: x['rerank_score'], reverse=True)
        
        return scored_results[:top_k]


# Global reranker instance (lazy loaded)
_reranker = None

def get_reranker() -> CrossEncoderReranker:
    """Get global reranker instance"""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker
