"""Shared schema pieces: base config, pagination, money rendering."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import format_pkr

T = TypeVar("T")


class Schema(BaseModel):
    """Base for every response model."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Money(Schema):
    """Money crosses the wire as both the integer and a ready display string.

    The frontend must never divide by 100 itself. Sending the formatted string
    alongside the exact integer means the backend and the UI can never disagree
    about how a price reads, and it keeps PKR formatting in one place.
    """

    paisa: int
    display: str

    @classmethod
    def of(cls, paisa: int, *, with_decimals: bool = False) -> Money:
        return cls(paisa=paisa, display=format_pkr(paisa, with_decimals=with_decimals))


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def of(cls, items: list[T], total: int, page: int, per_page: int) -> Page[T]:
        pages = (total + per_page - 1) // per_page if per_page else 0
        return cls(items=items, total=total, page=page, per_page=per_page, pages=pages)


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(24, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class Message(Schema):
    message: str
    ok: bool = True


class IdResponse(Schema):
    id: uuid.UUID


class Timestamped(Schema):
    created_at: datetime
    updated_at: datetime
