"""Narration synthesis (TTS) for the pipeline's narrator stage.

Resolves the narrator's TTS connection (Deepgram / ElevenLabs), synthesizes one
MP3 per scene, stores each in MinIO under ``audio/{project}/`` (anonymous-read,
like figures), and returns stable URLs + measured durations. The compiler turns
``params.audioUrl`` into HyperFrames ``<audio class="clip">`` elements, so the
same audio plays in the editor preview and the final render.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select

from vyakhya.core.logging import get_logger
from vyakhya.db.models.config import AgentModelAssignment, ProviderConnection
from vyakhya.enums import ProviderId, ProviderKind
from vyakhya.services import storage
from vyakhya.services.crypto import get_encryptor

log = get_logger(__name__)

# Deepgram caps speak input at 2000 chars; longer narration is synthesized in
# sentence-boundary chunks and the MP3 frames concatenated (same codec/rate),
# so the ENTIRE narration is always voiced — never truncated.
_MAX_TEXT = 1900


def _chunks(text: str, limit: int = _MAX_TEXT) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= limit:
        return [text]
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    cur = ""
    for sent in sentences:
        while len(sent) > limit:  # pathological run-on: hard-split
            out.append(sent[:limit])
            sent = sent[limit:]
        if len(cur) + len(sent) + 1 > limit and cur:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


async def resolve_tts_connection(session: Any) -> tuple[ProviderConnection, str] | None:
    """The narrator's TTS connection (or any TTS one) + decrypted API key."""
    assignment = await session.get(AgentModelAssignment, "narrator")
    conn: ProviderConnection | None = None
    if assignment is not None and assignment.connection_id:
        conn = await session.get(ProviderConnection, assignment.connection_id)
    if conn is None or conn.kind != ProviderKind.TTS:
        result = await session.execute(
            select(ProviderConnection)
            .where(ProviderConnection.kind == ProviderKind.TTS)
            .order_by(ProviderConnection.created_at)
        )
        conn = result.scalars().first()
    if conn is None:
        return None
    api_key = ""
    if conn.api_key_enc is not None:
        api_key = (await get_encryptor(session)).decrypt(conn.api_key_enc)
    return conn, api_key


async def synthesize(text: str, conn: ProviderConnection, api_key: str) -> bytes:
    """Full text → MP3 bytes via the connection's provider (chunked if long)."""
    text = text.strip()
    if not text:
        raise ValueError("empty narration text")
    parts: list[bytes] = []
    for chunk in _chunks(text):
        parts.append(await _synthesize_one(chunk, conn, api_key))
    return b"".join(parts)


async def _synthesize_one(text: str, conn: ProviderConnection, api_key: str) -> bytes:
    if conn.provider == ProviderId.DEEPGRAM:
        model = conn.model or "aura-2-thalia-en"
        url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=mp3"
        headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json={"text": text})
            resp.raise_for_status()
            return resp.content
    if conn.provider == ProviderId.ELEVENLABS:
        voice = conn.model or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url, headers=headers, json={"text": text, "model_id": "eleven_multilingual_v2"}
            )
            resp.raise_for_status()
            return resp.content
    raise ValueError(f"TTS provider {conn.provider} not supported for synthesis")


def mp3_duration_ms(data: bytes) -> int | None:
    """Measured clip length, so scene durations can stretch to fit narration."""
    try:
        import io

        from mutagen.mp3 import MP3

        return int(MP3(io.BytesIO(data)).info.length * 1000)
    except Exception as exc:  # noqa: BLE001 - duration is an enhancement
        log.warning("mp3 duration probe failed: %s", exc)
        return None


async def narrate_scene(
    project_id: str, index: int, text: str, conn: ProviderConnection, api_key: str
) -> tuple[str, int | None]:
    """Synthesize + store one scene's narration. Returns (url, duration_ms)."""
    data = await synthesize(text, conn, api_key)
    url = await storage.put_audio(project_id, index, data)
    return url, mp3_duration_ms(data)
