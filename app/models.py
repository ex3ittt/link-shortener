from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    # Only a SHA-256 of the manage token is stored, like a password.
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicks_total: Mapped[int] = mapped_column(Integer, default=0)

    clicks: Mapped[list["Click"]] = relationship(back_populates="link", cascade="all, delete-orphan", passive_deletes=True)


class Click(Base):
    __tablename__ = "clicks"
    __table_args__ = (Index("ix_clicks_link_time", "link_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    referrer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device: Mapped[str] = mapped_column(String(16))

    link: Mapped[Link] = relationship(back_populates="clicks")
