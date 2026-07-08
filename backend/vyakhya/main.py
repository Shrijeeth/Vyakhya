"""FastAPI application entrypoint for Vyakhya Studio.

Run: uvicorn vyakhya.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vyakhya import __version__

app = FastAPI(
    title="Vyakhya Studio API",
    version=__version__,
    description="Multi-agent engine that turns papers into detailed, editable explainer videos.",
)

# Dev CORS — the Vite frontend runs on a separate port during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Vyakhya Studio API", "docs": "/docs"}
