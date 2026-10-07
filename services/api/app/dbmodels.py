"""SQLAlchemy tables for the SaaS layer.

- User: accounts (email + bcrypt password hash).
- ProviderKey: a user's own LLM keys (OpenAI/Anthropic/Gemini), Fernet-encrypted.
- CustomEndpoint: any OpenAI-compatible / Ollama endpoint the user adds.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uid() -> str:
    return uuid.uuid4().hex[:16]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    provider_keys: Mapped[list["ProviderKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    endpoints: Mapped[list["CustomEndpoint"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class ProviderKey(Base):
    __tablename__ = "provider_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    provider: Mapped[str] = mapped_column(String(32), index=True)  # openai|anthropic|gemini
    model: Mapped[str] = mapped_column(String(120), default="")
    key_enc: Mapped[str] = mapped_column(Text)  # Fernet ciphertext
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    user: Mapped[User] = relationship(back_populates="provider_keys")


class CustomEndpoint(Base):
    __tablename__ = "custom_endpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    base_url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32), default="openai-compatible")
    model: Mapped[str] = mapped_column(String(120), default="")
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    user: Mapped[User] = relationship(back_populates="endpoints")
