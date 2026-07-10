"""Ingest step: crop the document's figures so the designer can put real
plots/diagrams on screen."""

from __future__ import annotations

from vyakhya.agents.context import PipelineContext
from vyakhya.core.database import get_sessionmaker
from vyakhya.core.logging import get_logger
from vyakhya.db.models.project import Project
from vyakhya.enums import AgentId

log = get_logger(__name__)


async def run(ctx: PipelineContext) -> None:
    async with ctx.stage(AgentId.INGESTOR, "Ingestor"):
        if ctx.paper_text.startswith("("):
            ctx.log(AgentId.INGESTOR, "Document text unavailable — designing from the title only.")
        if ctx.figures or not ctx.paper_file_url:
            return
        try:
            from vyakhya.services import storage
            from vyakhya.services.figures import extract_figures

            pdf_bytes = await storage.get_object(ctx.paper_file_url)
            ctx.figures = await extract_figures(ctx.project_id, pdf_bytes)
            sm = get_sessionmaker()
            async with sm() as session:
                project = await session.get(Project, ctx.project_id)
                if project is not None:
                    project.figures = ctx.figures
                    await session.commit()
            ctx.log(
                AgentId.INGESTOR,
                f"[Ingestor] extracted {len(ctx.figures)} figure(s) from the PDF",
            )
        except Exception as exc:  # noqa: BLE001 - figures are an enhancement
            log.warning("figure extraction failed: %s", exc)
            ctx.log(AgentId.INGESTOR, f"[Ingestor] figure extraction failed: {exc}")
