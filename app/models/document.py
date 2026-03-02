import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collections.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="text")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    collection = relationship("Collection", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("collection_id", "external_id", name="uq_document_collection_extid"),
        Index("idx_documents_metadata", "metadata_", postgresql_using="gin"),
    )
