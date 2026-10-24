from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class MemoryItem:
    scope: str
    kind: str  # fact | summary | episode | self
    content: str
    confidence: float = 1.0
    source_id: int | None = None
    created_at: float = 0.0


class MemoryBackend(Protocol):
    async def remember(self, item: MemoryItem) -> None: ...

    async def recall(self, scope: str, query: str, k: int) -> list[MemoryItem]: ...

    async def summary(self, scope: str) -> str: ...

    async def forget(self, scope: str, item_id: int) -> None: ...
