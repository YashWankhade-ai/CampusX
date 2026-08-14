"""
Multi-format document processing and semantic overlapping chunker for CampusX RAG System.
Supports PDF, Word (.docx), PowerPoint (.pptx), and Image OCR.
"""
import io
import os
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Fallback-safe imports for document formats
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import docx
except ImportError:
    docx = None

try:
    import pptx
except ImportError:
    pptx = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = pytesseract = None

class DocumentProcessor:
    @classmethod
    def extract_text(cls, file_bytes: bytes, filename: str, mime_type: str = "") -> str:
        """
        Extract plain text from PDF, Word (.docx), PowerPoint (.pptx), or Image (OCR).
        """
        ext = os.path.splitext(filename)[1].lower()

        # 1. PDF Processing
        if ext == ".pdf" or "pdf" in mime_type.lower():
            return cls._extract_pdf(file_bytes)

        # 2. Word Document Processing (.docx)
        elif ext in [".docx", ".doc"] or "word" in mime_type.lower() or "officedocument.wordprocessingml" in mime_type.lower():
            return cls._extract_docx(file_bytes)

        # 3. PowerPoint Presentation Processing (.pptx)
        elif ext in [".pptx", ".ppt"] or "powerpoint" in mime_type.lower() or "officedocument.presentationml" in mime_type.lower():
            return cls._extract_pptx(file_bytes)

        # 4. Image OCR Processing (.png, .jpg, .jpeg)
        elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"] or "image" in mime_type.lower():
            return cls._extract_image_ocr(file_bytes)

        # 5. Plain text fallback
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    @classmethod
    def _extract_pdf(cls, file_bytes: bytes) -> str:
        if not PyPDF2:
            return file_bytes.decode("utf-8", errors="ignore")
        try:
            pdf_file = io.BytesIO(file_bytes)
            reader = PyPDF2.PdfReader(pdf_file)
            text_pages = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                text_pages.append(f"[Page {i+1}]\n{page_text.strip()}")
            return "\n\n".join(text_pages)
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return file_bytes.decode("utf-8", errors="ignore")

    @classmethod
    def _extract_docx(cls, file_bytes: bytes) -> str:
        if not docx:
            return file_bytes.decode("utf-8", errors="ignore")
        try:
            doc_file = io.BytesIO(file_bytes)
            document = docx.Document(doc_file)
            paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Error extracting Docx text: {e}")
            return file_bytes.decode("utf-8", errors="ignore")

    @classmethod
    def _extract_pptx(cls, file_bytes: bytes) -> str:
        if not pptx:
            return file_bytes.decode("utf-8", errors="ignore")
        try:
            ppt_file = io.BytesIO(file_bytes)
            prs = pptx.Presentation(ppt_file)
            slides_text = []
            for i, slide in enumerate(prs.slides):
                slide_lines = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        slide_lines.append(shape.text.strip())
                if slide_lines:
                    slides_text.append(f"[Slide {i+1}]\n" + "\n".join(slide_lines))
            return "\n\n".join(slides_text)
        except Exception as e:
            logger.error(f"Error extracting PPTX text: {e}")
            return file_bytes.decode("utf-8", errors="ignore")

    @classmethod
    def _extract_image_ocr(cls, file_bytes: bytes) -> str:
        if not Image or not pytesseract:
            return "[OCR Output: OCR dependencies not installed. Image text placeholder.]"
        try:
            img = Image.open(io.BytesIO(file_bytes))
            ocr_text = pytesseract.image_to_string(img)
            return ocr_text.strip()
        except Exception as e:
            logger.error(f"Error extracting Image OCR text: {e}")
            return "[OCR Extraction Error]"

class SemanticChunker:
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
        """
        Splits raw text into overlapping semantic chunks with character indices.
        """
        if not text:
            return []

        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_chunk = ""
        current_words = 0

        for p in paragraphs:
            words = p.split()
            word_count = len(words)

            if current_words + word_count <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + p
                current_words += word_count
            else:
                if current_chunk:
                    chunks.append({"text": current_chunk.strip(), "word_count": current_words})

                # If single paragraph exceeds chunk size, split by words with overlap
                if word_count > chunk_size:
                    for i in range(0, word_count, chunk_size - overlap):
                        sub_words = words[i:i + chunk_size]
                        sub_text = " ".join(sub_words)
                        chunks.append({"text": sub_text.strip(), "word_count": len(sub_words)})
                    current_chunk = ""
                    current_words = 0
                else:
                    # Start new chunk with overlap from end of previous paragraph
                    prev_words = current_chunk.split()[-overlap:] if current_chunk else []
                    overlap_prefix = " ".join(prev_words)
                    current_chunk = (overlap_prefix + "\n\n" if overlap_prefix else "") + p
                    current_words = len(prev_words) + word_count

        if current_chunk:
            chunks.append({"text": current_chunk.strip(), "word_count": current_words})

        # Add chunk indices
        for idx, c in enumerate(chunks):
            c["chunk_index"] = idx

        return chunks
