"""
BM25 Sparse Keyword Search Service and Reciprocal Rank Fusion (RRF) for CampusX Hybrid RAG.
"""
import math
import re
from typing import List, Dict, Any, Tuple

def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text into lower-case terms."""
    return re.findall(r'\w+', text.lower())

class BM25Ranker:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def rank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Rank documents using BM25 scoring.
        Each doc is expected to have 'text', 'document_id', 'chunk_index'.
        """
        if not query or not documents:
            return []

        query_terms = tokenize(query)
        doc_count = len(documents)
        if doc_count == 0:
            return []

        # Tokenize documents
        doc_tokens_list = [tokenize(doc.get("text", "")) for doc in documents]
        doc_lengths = [len(dt) for dt in doc_tokens_list]
        avg_doc_len = sum(doc_lengths) / doc_count if doc_count > 0 else 1.0

        # Calculate Inverted Document Frequency (IDF) for query terms
        idf = {}
        for q_term in set(query_terms):
            n_q = sum(1 for dt in doc_tokens_list if q_term in dt)
            # Standard Lucene/BM25 IDF formula
            idf[q_term] = math.log((doc_count - n_q + 0.5) / (n_q + 0.5) + 1.0)

        # Compute BM25 scores
        scored_docs = []
        for idx, (doc, dt, doc_len) in enumerate(zip(documents, doc_tokens_list, doc_lengths)):
            score = 0.0
            term_freqs = {}
            for term in dt:
                term_freqs[term] = term_freqs.get(term, 0) + 1

            for q_term in query_terms:
                if q_term in term_freqs:
                    tf = term_freqs[q_term]
                    num = tf * (self.k1 + 1.0)
                    den = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / avg_doc_len))
                    score += idf.get(q_term, 0.0) * (num / den)

            if score > 0:
                doc_copy = dict(doc)
                doc_copy["bm25_score"] = score
                scored_docs.append(doc_copy)

        scored_docs.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored_docs[:top_k]

def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    k: int = 60,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Combines dense vector search results and sparse BM25 search results using Reciprocal Rank Fusion (RRF).
    Formula: RRF_Score(doc) = 1 / (k + rank_dense) + 1 / (k + rank_sparse)
    """
    rrf_map: Dict[str, Dict[str, Any]] = {}

    # 1. Process Dense Results
    for rank, doc in enumerate(dense_results, start=1):
        doc_key = f"{doc.get('document_id')}_{doc.get('chunk_index', 0)}"
        if doc_key not in rrf_map:
            rrf_map[doc_key] = {
                "doc": doc,
                "rrf_score": 0.0,
                "dense_score": doc.get("score", 0.0),
                "bm25_score": 0.0
            }
        rrf_map[doc_key]["rrf_score"] += 1.0 / (k + rank)

    # 2. Process Sparse BM25 Results
    for rank, doc in enumerate(sparse_results, start=1):
        doc_key = f"{doc.get('document_id')}_{doc.get('chunk_index', 0)}"
        if doc_key not in rrf_map:
            rrf_map[doc_key] = {
                "doc": doc,
                "rrf_score": 0.0,
                "dense_score": 0.0,
                "bm25_score": doc.get("bm25_score", 0.0)
            }
        rrf_map[doc_key]["rrf_score"] += 1.0 / (k + rank)
        rrf_map[doc_key]["bm25_score"] = doc.get("bm25_score", 0.0)

    # 3. Sort by combined RRF score
    fused_list = list(rrf_map.values())
    fused_list.sort(key=lambda x: x["rrf_score"], reverse=True)

    results = []
    for item in fused_list[:top_k]:
        doc = dict(item["doc"])
        doc["score"] = round(item["rrf_score"], 4)
        doc["dense_score"] = item["dense_score"]
        doc["bm25_score"] = item["bm25_score"]
        results.append(doc)

    return results
