import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collections.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="processing")
    total_docs: Mapped[int] = mapped_column(Integer, default=0)
    processed_docs: Mapped[int] = mapped_column(Integer, default=0)
    failed_docs: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    collection = relationship("Collection", back_populates="ingestion_jobs")
    documents = relationship("Document", back_populates="ingestion_job")
