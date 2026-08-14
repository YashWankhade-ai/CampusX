import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Text, Float
from app.models.base import BaseModel

class EmbeddingModelConfig(BaseModel):
    __tablename__ = "embedding_model_configs"
    model_name: Mapped[str] = mapped_column(String(100), unique=True)
    dimension: Mapped[int] = mapped_column(default=1536)
    is_active: Mapped[bool] = mapped_column(default=True)

class ResourceChunk(BaseModel):
    __tablename__ = "resource_chunks"
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("study_materials.id"))
    chunk_index: Mapped[int] = mapped_column(default=0)
    content: Mapped[str] = mapped_column(Text)

class ChunkEmbedding(BaseModel):
    __tablename__ = "chunk_embeddings"
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resource_chunks.id"))
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("embedding_model_configs.id"))
    vector_id: Mapped[str] = mapped_column(String(255)) # ID in Qdrant
