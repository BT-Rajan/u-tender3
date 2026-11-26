from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import DateTime, gen_uuid


class OfferQuotation(Base):
    """A contractor's quotation file for a tender. Uploaded on the WhatsApp offer form, held until the offer is
    submitted, then linked to that offer."""

    __tablename__ = "offer_quotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    offer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contractor_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
