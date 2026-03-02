import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(50), default="bge-m3")
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1024)
    chunk_strategy: Mapped[str] = mapped_column(String(30), default="adaptive")
    chunk_size: Mapped[int] = mapped_column(Integer, default=512)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50)
    metadata_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    language: Mapped[str] = mapped_column(String(10), default="auto")
    doc_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    organization = relationship("Organization", back_populates="collections")
    api_keys = relationship("ApiKey", back_populates="collection", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="collection", cascade="all, delete-orphan")
    ingestion_jobs = relationship(
        "IngestionJob", back_populates="collection", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_collection_org_name"),
    )
