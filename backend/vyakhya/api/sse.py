"""Server-Sent Events helpers.

Each pipeline/render event is emitted as one SSE `data:` frame carrying the JSON
payload — a 1:1 map to the wire event shapes in docs/api.md, consumed by the
frontend's subscribe callbacks.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse

from vyakhya.core.events import broker

_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _frame(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _iter(topic: str) -> AsyncIterator[str]:
    q = broker.register(topic)
    async for event in broker.stream(topic, q):
        yield _frame(event)


def sse_response(topic: str) -> StreamingResponse:
    """Stream events for `topic` — the caller must have already registered the
    producer AFTER calling `broker.register` implicitly here. Prefer
    `sse_response_with_producer` when a producer must be launched.
    """
    return StreamingResponse(_iter(topic), media_type="text/event-stream", headers=_HEADERS)


def sse_response_with_producer(topic: str, launch) -> StreamingResponse:
    """Register the subscriber, launch the producer, then stream — guaranteeing
    no early events are dropped.
    """

    async def gen() -> AsyncIterator[str]:
        q = broker.register(topic)
        launch()
        async for event in broker.stream(topic, q):
            yield _frame(event)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_HEADERS)
