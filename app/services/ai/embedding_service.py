from typing import List, Dict, Any, Optional
try:
    import pypdf as PyPDF2
except ImportError:
    try:
        import PyPDF2
    except ImportError:
        PyPDF2 = None
import io
from .clients import AIClients

class DocumentChunker:
    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

    @staticmethod
    def semantic_chunking(text: str, max_chunk_size: int = 1000, overlap: int = 200) -> List[Dict[str, Any]]:
        # A basic semantic chunking that splits by paragraphs and combines them up to max_chunk_size
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        
        for p in paragraphs:
            if len(current_chunk) + len(p) <= max_chunk_size:
                current_chunk += p + "\n\n"
            else:
                if current_chunk:
                    chunks.append({"text": current_chunk.strip()})
                
                # If a single paragraph is larger than chunk size, just add it (or could split by sentences)
                if len(p) > max_chunk_size:
                    # simplistic split by chunks
                    for i in range(0, len(p), max_chunk_size - overlap):
                        chunks.append({"text": p[i:i+max_chunk_size].strip()})
                    current_chunk = ""
                else:
                    # Start new chunk with overlap from previous if possible (simplified here)
                    current_chunk = p + "\n\n"
                    
        if current_chunk:
            chunks.append({"text": current_chunk.strip()})
            
        return chunks

class EmbeddingService:
    def __init__(self, ai_clients: Optional[AIClients] = None):
        self.clients = ai_clients if ai_clients is not None else AIClients()
        self.chunker = DocumentChunker()

    async def get_embedding(self, text: str) -> List[float]:
        return await self.clients.get_embedding(text)

    async def batch_embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[List[float]]:
        # In a real scenario, this would use a batch API or concurrent requests
        embeddings = []
        for chunk in chunks:
            emb = await self.get_embedding(chunk["text"])
            embeddings.append(emb)
        return embeddings
