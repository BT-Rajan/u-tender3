from datetime import datetime

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import DateTime


# A setting an admin edits in the app. A value saved here overrides the server's .env value.
# Secret values are stored encrypted (see app/services/app_settings.py).
class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
