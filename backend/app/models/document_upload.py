from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


class DocumentUploadLink(Base):
    """A short-lived, single-use link that lets one user upload one requirement's document.

    Only SHA-256 hashes of the link token and the one-time code are stored, so a
    leaked table can't be used to upload. The link is bound to a user and a
    requirement. It is burned on a successful upload, after too many wrong codes,
    or when a newer link for the same requirement replaces it.
    """

    __tablename__ = "document_upload_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_requirements.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    wrong_code_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentVersion(Base):
    """One uploaded file for a requirement, kept for audit when it is replaced.

    The live file stays on the contractor_documents / owner_documents row. This
    table is the history: every upload, with its hash and size, and when a later
    upload superseded it. Old files are never deleted, so an admin can always see
    what was reviewed.
    """

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("file_path", name="uq_document_version_path"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "owner" | "contractor"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_requirements.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # "web" | "whatsapp"
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
