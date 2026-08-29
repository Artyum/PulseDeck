from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigInt
from app.models.enums import EmailOutboxPriority, EmailOutboxStatus


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    priority: Mapped[EmailOutboxPriority] = mapped_column(
        Enum(
            EmailOutboxPriority,
            name="email_outbox_priority",
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    list_unsubscribe_url: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    status: Mapped[EmailOutboxStatus] = mapped_column(
        Enum(
            EmailOutboxStatus, name="email_outbox_status", native_enum=False, length=20
        ),
        nullable=False,
        default=EmailOutboxStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
