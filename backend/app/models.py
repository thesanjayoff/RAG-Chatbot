from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Table, Text, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", String, ForeignKey("documents.id"), primary_key=True),
    Column("tag_id", String, ForeignKey("tags.id"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)

    documents: Mapped[list["Document"]] = relationship(
        "Document", secondary=document_tags, back_populates="tags"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    filename: Mapped[str] = mapped_column(String)
    stored_path: Mapped[str] = mapped_column(String)  # path under data/documents
    file_type: Mapped[str] = mapped_column(String)  # pdf, docx, pptx, xlsx, csv, md, txt, html, image
    file_hash: Mapped[str] = mapped_column(String, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    source_type: Mapped[str] = mapped_column(String, default="upload")  # upload | watched_folder | url
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)  # original fs path or URL
    watched_folder_id: Mapped[str | None] = mapped_column(String, ForeignKey("watched_folders.id"), nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending")  # pending|processing|ready|error|skipped
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)

    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    used_ocr: Mapped[bool] = mapped_column(default=False)

    secrets_flag: Mapped[bool] = mapped_column(default=False)
    secrets_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    injection_flag: Mapped[bool] = mapped_column(default=False)
    injection_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    doc_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags: Mapped[list[Tag]] = relationship("Tag", secondary=document_tags, back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)

    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")


class WatchedFolder(Base):
    __tablename__ = "watched_folders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    path: Mapped[str] = mapped_column(String, unique=True)
    recursive: Mapped[bool] = mapped_column(default=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(String, ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    retrieved_chunks: Mapped[list | None] = mapped_column(JSON, nullable=True)  # debug: what was retrieved
    not_found: Mapped[bool] = mapped_column(default=False)
    used_general_knowledge: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
