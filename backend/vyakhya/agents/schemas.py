"""Structured-output schemas for the pipeline agents, plus the parsing
helpers that keep imperfect model JSON usable (fence-stripping, truncation
salvage, per-scene recovery, index-based patching)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vyakhya.core.logging import get_logger
from vyakhya.enums import CaptionStyle, SceneTransition, VisualType

log = get_logger(__name__)


# ── Scenes (the designer's output) ─────────────────────────────────────────────
class GenCitation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str
    source_span: str = Field(alias="sourceSpan")


class GenSeriesPoint(BaseModel):
    label: str
    value: float


class GenSceneParams(BaseModel):
    """Union of every visual type's params, all optional — a closed schema so
    provider-native structured output works everywhere."""

    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    subtitle: str | None = None
    bullets: list[str] | None = None
    caption: str | None = None
    figure_ref: str | None = Field(default=None, alias="figureRef")
    figure_id: str | None = Field(default=None, alias="figureId")
    figure_url: str | None = Field(default=None, alias="figureUrl")
    latex: str | None = None
    series: list[GenSeriesPoint] | None = None
    tokens: list[str] | None = None
    left: str | None = None
    right: str | None = None
    text: str | None = None
    # custom.html — agent-authored stage markup + styles (no scripts).
    html: str | None = None
    css: str | None = None
    # Narration audio, attached by the pipeline (never by the model).
    audio_url: str | None = Field(default=None, alias="audioUrl")
    audio_duration_ms: int | None = Field(default=None, alias="audioDurationMs")


class GenScene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 0-based position — revision replies return ONLY changed scenes, each
    # carrying the index of the scene it replaces.
    index: int | None = None
    narration: str = ""
    visual_type: VisualType = Field(alias="visualType")
    params: GenSceneParams = Field(default_factory=GenSceneParams)
    caption_style: CaptionStyle = Field(default=CaptionStyle.MINIMAL, alias="captionStyle")
    transition: SceneTransition = SceneTransition.FADE
    duration_ms: int = Field(default=6000, alias="durationMs")
    citations: list[GenCitation] = Field(default_factory=list)

    @field_validator("duration_ms", mode="after")
    @classmethod
    def _clamp_duration(cls, v: int) -> int:
        return min(max(v, 1000), 60_000)

    # Cosmetic enums must never kill a scene — coerce unknowns to defaults.
    @field_validator("caption_style", mode="before")
    @classmethod
    def _lenient_caption(cls, v: object) -> object:
        try:
            return CaptionStyle(v)  # type: ignore[arg-type]
        except ValueError:
            return CaptionStyle.MINIMAL

    @field_validator("transition", mode="before")
    @classmethod
    def _lenient_transition(cls, v: object) -> object:
        try:
            return SceneTransition(v)  # type: ignore[arg-type]
        except ValueError:
            return SceneTransition.FADE


class GenDocument(BaseModel):
    scenes: list[GenScene]


# ── Review report ──────────────────────────────────────────────────────────────
class ReviewIssue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scene_index: int = Field(alias="sceneIndex")
    problem: str
    fix: str
    severity: Literal["minor", "major"] = "major"


class ReviewReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    approved: bool
    issues: list[ReviewIssue] = Field(default_factory=list)


# ── Parsing helpers ────────────────────────────────────────────────────────────
def extract_data(content: object) -> dict | list | None:
    """Get a plain dict/list out of whatever an agent returned (model
    instance, dict, or raw/fenced JSON string)."""
    if isinstance(content, BaseModel):
        return content.model_dump(by_alias=True)
    if isinstance(content, dict | list):
        return content
    if isinstance(content, str):
        import json
        import re

        text = content.strip()
        fence = re.search(r"```(?:json)?\s*([\[{].*[\]}])\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                try:
                    return json.loads(brace.group(0))
                except Exception:  # noqa: BLE001
                    return None
            return None
    return None


def salvage_scene_objects(text: str) -> list | None:
    """Recover complete scene objects from a TRUNCATED response (output-token
    cap hit mid-JSON): decode objects one by one and drop the broken tail."""
    import json
    import re

    m = re.search(r'"scenes"\s*:\s*\[', text)
    start = m.end() if m else (text.find("[") + 1 if text.lstrip().startswith("[") else -1)
    if start <= 0:
        return None
    dec = json.JSONDecoder()
    idx, n, out = start, len(text), []
    while idx < n:
        while idx < n and text[idx] in " \t\r\n,":
            idx += 1
        if idx >= n or text[idx] == "]":
            break
        try:
            obj, idx = dec.raw_decode(text, idx)
        except Exception:  # noqa: BLE001 - truncation point reached
            break
        out.append(obj)
    return out or None


def coerce_document(content: object) -> GenDocument | None:
    """Normalize agent output to a GenDocument, salvaging what validates."""
    if isinstance(content, GenDocument):
        return content
    data = extract_data(content)
    if data is None and isinstance(content, str):
        salvaged = salvage_scene_objects(content)
        if salvaged:
            log.warning("response truncated — salvaged %d complete scene(s)", len(salvaged))
            data = {"scenes": salvaged}
    if data is None:
        return None
    if isinstance(data, list):
        data = {"scenes": data}
    try:
        return GenDocument.model_validate(data)
    except Exception:  # noqa: BLE001 - fall through to per-scene salvage
        pass
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list):
        return None
    scenes: list[GenScene] = []
    for i, raw in enumerate(raw_scenes):
        try:
            scenes.append(GenScene.model_validate(raw))
        except Exception as exc:  # noqa: BLE001 - drop just this scene
            log.warning("dropping invalid scene %d: %s", i, exc)
    return GenDocument(scenes=scenes) if scenes else None


def coerce_model(content: object, model_cls: type) -> object | None:
    """Normalize agent output to ``model_cls`` (report schemas)."""
    if isinstance(content, model_cls):
        return content
    data = extract_data(content)
    if not isinstance(data, dict):
        return None
    try:
        return model_cls.model_validate(data)
    except Exception:  # noqa: BLE001 - report unusable
        return None


def patch_scenes(doc: GenDocument, revised: GenDocument) -> int:
    """Apply a partial revision: each revised scene replaces the scene at its
    0-based ``index``. An unindexed reply is applied wholesale ONLY when it
    is at least the size of the current cut (a shorter one is truncation)."""
    indexed = [sc for sc in revised.scenes if sc.index is not None]
    if indexed:
        patched = 0
        for sc in indexed:
            if 0 <= sc.index < len(doc.scenes):
                doc.scenes[sc.index] = sc
                patched += 1
        return patched
    if len(revised.scenes) >= len(doc.scenes):
        doc.scenes = revised.scenes
        return len(revised.scenes)
    return 0


def normalize_scene_params(scene: GenScene) -> None:
    """Repair params filed under a sibling key so every visual renders."""
    p = scene.params
    vt = scene.visual_type
    if vt is VisualType.KINETIC_TYPE and not p.text:
        p.text = " ".join(p.tokens) if p.tokens else (p.title or p.caption or scene.narration[:80])
    elif vt is VisualType.DIAGRAM_ATTENTION and not p.tokens:
        source = p.caption or p.text or scene.narration
        p.tokens = p.bullets or (source.split()[:8] if source else None)
    elif vt is VisualType.BULLET_REVEAL and not p.bullets:
        p.bullets = p.tokens
    elif vt is VisualType.TITLE_CARD and not p.title:
        p.title = p.text or p.caption or scene.narration[:60]
    elif vt is VisualType.FIGURE_CALLOUT and not p.caption:
        p.caption = p.text or p.title
    elif vt is VisualType.EQUATION_BUILD and not p.latex:
        p.latex = p.text
    elif vt is VisualType.COMPARISON_SPLIT and not (p.left and p.right):
        if p.bullets and len(p.bullets) >= 2:
            p.left, p.right = p.left or p.bullets[0], p.right or p.bullets[1]
    elif vt is VisualType.ORBIT_3D and not p.tokens:
        source = p.title or p.text or p.caption or scene.narration
        p.tokens = p.bullets or (source.split()[:6] if source else None)
    elif vt is VisualType.CUSTOM_HTML:
        html = p.html or ""
        unstyled = "class=" in html and not p.css and "style=" not in html
        if not html.strip() or unstyled:
            scene.visual_type = VisualType.KINETIC_TYPE
            import re as _re

            plain = _re.sub(r"<[^>]+>", " ", html).strip()
            p.text = p.text or plain[:80] or p.title or p.caption or scene.narration[:80]


def dump_scenes(doc: GenDocument, figure_map: dict[str, str] | None = None) -> list[dict]:
    """Scene dicts for persistence/preview, with figure ids resolved to URLs."""
    fmap = figure_map or {}
    for s in doc.scenes:
        normalize_scene_params(s)
        p = s.params
        if p.figure_id:
            url = fmap.get(p.figure_id)
            p.figure_url = url
            if url is None:
                p.figure_id = None
    used = {s.params.figure_id for s in doc.scenes if s.params.figure_id}
    unused = [(fid, url) for fid, url in fmap.items() if fid not in used]
    for s in doc.scenes:
        if s.visual_type is VisualType.FIGURE_CALLOUT and not s.params.figure_url and unused:
            fid, url = unused.pop(0)
            s.params.figure_id, s.params.figure_url = fid, url
    return [s.model_dump(by_alias=True, exclude_none=True) for s in doc.scenes]


def scenes_json(doc: GenDocument) -> str:
    import json

    return json.dumps(
        [s.model_dump(by_alias=True, exclude_none=True) for s in doc.scenes], indent=1
    )
