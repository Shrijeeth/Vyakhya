"""Figure extraction — crop the paper's figures out of the PDF.

Runs in the pipeline's ingestor stage (PyMuPDF, `agents` extra). Two-pass:
embedded raster images first (the common case for plots/diagrams), falling
back to rendering full pages when a PDF has none (vector-only papers).
Crops are uploaded to MinIO under the public-read ``figures/`` prefix so the
compiled composition can embed them with stable URLs.
"""

from __future__ import annotations

import asyncio

from vyakhya.core.logging import get_logger
from vyakhya.services import storage

log = get_logger(__name__)

_MIN_DIM = 140  # px — skip icons/rules
_MIN_AREA = 60_000  # px² — skip small decorations
_MAX_FIGURES = 12


def _extract_sync(pdf_bytes: bytes) -> list[dict]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: list[dict] = []
    seen_digests: set[str] = set()
    for page_index in range(doc.page_count):
        page = doc[page_index]
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha > 3:  # CMYK etc → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
            except Exception:  # noqa: BLE001 - unreadable image object
                continue
            if pix.width < _MIN_DIM or pix.height < _MIN_DIM:
                continue
            if pix.width * pix.height < _MIN_AREA:
                continue
            png = pix.tobytes("png")
            digest = str(hash(png))
            if digest in seen_digests:  # repeated logos/headers
                continue
            seen_digests.add(digest)
            out.append(
                {
                    "page": page_index + 1,
                    "width": pix.width,
                    "height": pix.height,
                    "png": png,
                }
            )
            if len(out) >= _MAX_FIGURES:
                doc.close()
                return out
    doc.close()
    return out


async def extract_figures(project_id: str, pdf_bytes: bytes) -> list[dict]:
    """Crop figures and upload them. Returns [{id,page,width,height,url}]."""
    raw = await asyncio.to_thread(_extract_sync, pdf_bytes)
    figures: list[dict] = []
    for i, f in enumerate(raw, start=1):
        try:
            url = await storage.put_figure(project_id, i, f.pop("png"))
        except Exception as exc:  # noqa: BLE001 - storage down → skip figure
            log.warning("figure upload failed (fig%d): %s", i, exc)
            continue
        figures.append({"id": f"fig{i}", "url": url, **f})
    log.info("extracted %d figure(s) for project %s", len(figures), project_id)
    return figures
