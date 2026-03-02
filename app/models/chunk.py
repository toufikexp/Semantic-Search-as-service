import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document = relationship("Document", back_populates="chunks")
    embeddings = relationship("Embedding", back_populates="chunk", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_chunks_doc", "collection_id", "document_id"),
    )
