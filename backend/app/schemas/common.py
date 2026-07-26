"""Shared schema building blocks."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, Field

#: Offset pagination, deliberately. Cursor pagination is better under concurrent inserts, but
#: this application's lists are per-user and small — a company has tens of evidence items, not
#: millions — and offsets let the frontend jump to a page and show a total count.
DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100

PageLimit = Annotated[int, Field(ge=1, le=MAX_PAGE_LIMIT)]
PageOffset = Annotated[int, Field(ge=0)]


class Page[ItemT](BaseModel):
    """One page of results plus enough metadata to render a pager."""

    items: list[ItemT]
    total: int = Field(description="Total rows matching the filters, ignoring limit/offset.")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total

    @classmethod
    def build(cls, items: list[ItemT], *, total: int, limit: int, offset: int) -> Self:
        return cls(items=items, total=total, limit=limit, offset=offset)
