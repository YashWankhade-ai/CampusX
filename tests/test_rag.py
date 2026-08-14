import pytest
from app.services.ai.document_processor import DocumentProcessor, SemanticChunker
from app.services.ai.bm25_service import BM25Ranker, reciprocal_rank_fusion
from app.tasks.indexing import index_document_task

def test_document_processor_text_extraction():
    plain_text = b"Introduction to Computer Science and Data Structures."
    extracted = DocumentProcessor.extract_text(plain_text, "cs101.txt", "text/plain")
    assert "Computer Science" in extracted

def test_semantic_chunker():
    text = "Paragraph 1: Data Structures.\n\nParagraph 2: Sorting Algorithms and Complexity.\n\nParagraph 3: Dynamic Programming."
    chunks = SemanticChunker.chunk_text(text, chunk_size=20, overlap=5)
    assert len(chunks) >= 1
    assert "chunk_index" in chunks[0]

def test_bm25_and_rrf_fusion():
    query = "Sorting Algorithms"
    docs = [
        {"document_id": "doc1", "text": "Sorting Algorithms such as QuickSort and MergeSort", "chunk_index": 0},
        {"document_id": "doc2", "text": "Database indexing and SQL queries", "chunk_index": 0}
    ]

    ranker = BM25Ranker()
    sparse_results = ranker.rank(query, docs, top_k=2)
    assert len(sparse_results) >= 1
    assert sparse_results[0]["document_id"] == "doc1"

    dense_results = [
        {"document_id": "doc1", "chunk_index": 0, "score": 0.88},
        {"document_id": "doc2", "chunk_index": 0, "score": 0.42}
    ]

    fused = reciprocal_rank_fusion(dense_results, sparse_results, top_k=2)
    assert len(fused) >= 1
    assert fused[0]["document_id"] == "doc1"

def test_hybrid_search_api_endpoint(client):
    res = client.get("/api/v1/search?q=Algorithms&limit=5")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "meta" in data
    assert data["meta"]["query"] == "Algorithms"

def test_celery_indexing_background_task():
    # Test execution of Celery background task
    res = index_document_task.delay(
        material_id="00000000-0000-0000-0000-000000000000",
        file_path="non_existent_sample.pdf",
        metadata={"title": "Test Material"}
    )
    assert res is not None
