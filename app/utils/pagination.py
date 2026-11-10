from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.utils.parse import parse_positive_int

T = TypeVar("T")
PageArg = int | str | None

PAGE_SIZE_DEFAULT = 25
PAGE_SIZES = (10, PAGE_SIZE_DEFAULT, 50)


def normalize_page_size(value: PageArg) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return PAGE_SIZE_DEFAULT
    return n if n in PAGE_SIZES else PAGE_SIZE_DEFAULT


def last_page_of(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size)) if total else 1


def page_window(page: PageArg, total: int, page_size: PageArg) -> tuple[int, int, int]:
    size = normalize_page_size(page_size)
    page_n = min(parse_positive_int(page), last_page_of(total, size))
    return page_n, (page_n - 1) * size, size


@dataclass(frozen=True)
class PageResult(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def last_page(self) -> int:
        return last_page_of(self.total, self.page_size)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.last_page

    @property
    def range_start(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.page_size + 1

    @property
    def range_end(self) -> int:
        return min(self.page * self.page_size, self.total)


def empty_page(page_size: PageArg = None) -> PageResult:
    return PageResult(
        items=[],
        total=0,
        page=1,
        page_size=normalize_page_size(page_size),
    )


def paginate_list(
    items: Sequence[T], page: PageArg, page_size: PageArg
) -> PageResult[T]:
    total = len(items)
    page_n, offset, size = page_window(page, total, page_size)
    return PageResult(
        items=list(items[offset : offset + size]),
        total=total,
        page=page_n,
        page_size=size,
    )
