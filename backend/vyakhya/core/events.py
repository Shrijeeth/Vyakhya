"""In-process async pub/sub broker for streaming (SSE) pipeline & render events.

Subscribers register an `asyncio.Queue` on a topic (a pipeline run id or render
job id), then iterate it. Publishers push JSON-serializable dicts. Register
BEFORE launching the producer so no early events are missed. Sufficient for a
single API process; the multi-process path (API + Procrastinate worker) swaps
this for Postgres `LISTEN/NOTIFY` behind the same interface.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

_SENTINEL: Any = object()


class EventBroker:
    def __init__(self) -> None:
        self._topics: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def register(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._topics[topic].add(q)
        return q

    def unregister(self, topic: str, q: asyncio.Queue) -> None:
        self._topics[topic].discard(q)
        if not self._topics[topic]:
            self._topics.pop(topic, None)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        for q in list(self._topics.get(topic, ())):
            q.put_nowait(event)

    async def close(self, topic: str) -> None:
        """Signal all subscribers of `topic` that the stream has ended."""
        for q in list(self._topics.get(topic, ())):
            q.put_nowait(_SENTINEL)

    async def stream(self, topic: str, q: asyncio.Queue) -> AsyncIterator[dict[str, Any]]:
        try:
            while True:
                item = await q.get()
                if item is _SENTINEL:
                    return
                yield item
        finally:
            self.unregister(topic, q)


# Process-wide singleton.
broker = EventBroker()
