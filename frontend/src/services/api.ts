// Typed API service layer. Currently backed by in-memory mocks + simulated
// latency. Real REST / WebSocket / SSE calls plug in here — screens keep
// importing these functions unchanged.

import type {
  AgentId,
  AgentModelAssignment,
  AgentPrompt,
  EditorProject,
  PipelineEvent,
  Project,
  ProviderConnection,
  RenderJob,
  RenderSettings,
  Scene,
  VerifierFlag,
} from "./types";
import {
  defaultRenderSettings,
  mockAssignments,
  mockConnections,
  mockEditorProject,
  mockProjects,
  mockPrompts,
  mockVerifierFlags,
} from "./mock-data";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---------------- Projects ----------------
let projectsMem = [...mockProjects];

export async function listProjects(): Promise<Project[]> {
  await sleep(200);
  return projectsMem;
}

export async function getProject(id: string): Promise<Project | undefined> {
  await sleep(120);
  return projectsMem.find((p) => p.id === id);
}

export async function createProject(input: {
  file: File;
  audience: Project["audience"];
  aspectRatio: Project["aspectRatio"];
  language: string;
  targetLengthMin: number;
}): Promise<Project> {
  await sleep(400);
  const p: Project = {
    id: `p${Date.now()}`,
    title: input.file.name.replace(/\.pdf$/i, ""),
    sourcePaper: input.file.name,
    status: "generating",
    durationMs: 0,
    updatedAt: new Date().toISOString(),
    audience: input.audience,
    aspectRatio: input.aspectRatio,
    language: input.language,
  };
  projectsMem = [p, ...projectsMem];
  return p;
}

// ---------------- Pipeline ----------------
const AGENT_SEQUENCE: { id: AgentId; label: string }[] = [
  { id: "ingestor", label: "Ingestor" },
  { id: "comprehension", label: "Comprehension" },
  { id: "planner", label: "Planner" },
  { id: "scriptwriter", label: "Scriptwriter" },
  { id: "visual_designer", label: "Visual Designer" },
  { id: "narrator", label: "Narrator" },
  { id: "verifier", label: "Verifier" },
  { id: "assembler", label: "Assembler" },
];

export function getAgentSequence() {
  return AGENT_SEQUENCE;
}

// Simulated WebSocket/SSE — call onEvent with a stream of pipeline events.
// Returns an unsubscribe function.
export function subscribePipeline(
  _projectId: string,
  onEvent: (event: PipelineEvent) => void,
): () => void {
  let cancelled = false;
  const timeouts: ReturnType<typeof setTimeout>[] = [];
  const schedule = (delay: number, fn: () => void) => {
    const t = setTimeout(() => {
      if (!cancelled) fn();
    }, delay);
    timeouts.push(t);
  };

  const stepDuration = 2000;
  let cursor = 300;
  AGENT_SEQUENCE.forEach((agent, idx) => {
    schedule(cursor, () => onEvent({ type: "status", agentId: agent.id, payload: "running" }));
    // interleave logs
    for (let l = 0; l < 3; l++) {
      schedule(cursor + 200 + l * 400, () =>
        onEvent({
          type: "log",
          agentId: agent.id,
          payload: `[${agent.label}] step ${l + 1}/3 …`,
        }),
      );
    }
    schedule(cursor + stepDuration, () => {
      onEvent({
        type: "status",
        agentId: agent.id,
        payload: "done",
      });
      onEvent({ type: "progress", payload: (idx + 1) / AGENT_SEQUENCE.length });
      if (agent.id === "verifier") {
        mockVerifierFlags.forEach((f) => onEvent({ type: "flag", payload: f }));
      }
      if (idx === AGENT_SEQUENCE.length - 1) {
        onEvent({ type: "done", payload: null });
      }
    });
    cursor += stepDuration + 400;
  });

  return () => {
    cancelled = true;
    timeouts.forEach((t) => clearTimeout(t));
  };
}

export async function getVerifierFlags(_projectId: string): Promise<VerifierFlag[]> {
  await sleep(120);
  return mockVerifierFlags;
}

// ---------------- Editor ----------------
export async function getEditorProject(_id: string): Promise<EditorProject> {
  await sleep(200);
  return structuredClone(mockEditorProject);
}

export async function saveScene(_projectId: string, scene: Scene): Promise<Scene> {
  await sleep(150);
  return scene;
}

// Placeholder for the live HTML preview compile. In production this hits
// the HyperFrames renderer; here we return a themed HTML string.
export async function compileScenePreview(scene: Scene): Promise<string> {
  await sleep(80);
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;height:100%;font-family:Inter,system-ui,sans-serif;background:#faf7f0;color:#1c1e2e}
    .stage{display:flex;align-items:center;justify-content:center;height:100%;padding:6% 8%;box-sizing:border-box;text-align:center}
    .card{max-width:900px}
    h1{font-size:56px;line-height:1.1;margin:0 0 16px;letter-spacing:-0.02em}
    p{font-size:22px;line-height:1.5;color:#4a4f66;margin:0}
    .tag{display:inline-block;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#4b3fbf;background:#eae7ff;padding:6px 12px;border-radius:999px;margin-bottom:20px}
  </style></head><body><div class="stage"><div class="card">
    <div class="tag">${scene.visualType}</div>
    <h1>Scene ${scene.index}</h1>
    <p>${scene.narration.replace(/</g, "&lt;")}</p>
  </div></div></body></html>`;
}

// ---------------- Model config ----------------
let connectionsMem = [...mockConnections];
let assignmentsMem = [...mockAssignments];

export async function listConnections(): Promise<ProviderConnection[]> {
  await sleep(120);
  return connectionsMem;
}
export async function addConnection(
  c: Omit<ProviderConnection, "id" | "status">,
): Promise<ProviderConnection> {
  await sleep(200);
  const next: ProviderConnection = { ...c, id: `c${Date.now()}`, status: "unknown" };
  connectionsMem = [...connectionsMem, next];
  return next;
}
export async function removeConnection(id: string): Promise<void> {
  await sleep(120);
  connectionsMem = connectionsMem.filter((c) => c.id !== id);
  assignmentsMem = assignmentsMem.map((a) =>
    a.connectionId === id ? { ...a, connectionId: null } : a,
  );
}
export async function testConnection(id: string): Promise<ProviderConnection> {
  await sleep(700);
  connectionsMem = connectionsMem.map((c) =>
    c.id === id ? { ...c, status: "ok", lastTestedAt: new Date().toISOString() } : c,
  );
  return connectionsMem.find((c) => c.id === id)!;
}
export async function listAssignments(): Promise<AgentModelAssignment[]> {
  await sleep(80);
  return assignmentsMem;
}
export async function updateAssignment(
  role: AgentModelAssignment["role"],
  connectionId: string | null,
) {
  await sleep(80);
  assignmentsMem = assignmentsMem.map((a) => (a.role === role ? { ...a, connectionId } : a));
  return assignmentsMem;
}

// ---------------- Prompts ----------------
let promptsMem = [...mockPrompts];
export async function listPrompts(): Promise<AgentPrompt[]> {
  await sleep(120);
  return promptsMem;
}
export async function savePrompt(id: AgentId, template: string): Promise<AgentPrompt> {
  await sleep(120);
  promptsMem = promptsMem.map((p) => (p.id === id ? { ...p, template } : p));
  return promptsMem.find((p) => p.id === id)!;
}
export async function resetPrompt(id: AgentId): Promise<AgentPrompt> {
  await sleep(120);
  promptsMem = promptsMem.map((p) => (p.id === id ? { ...p, template: p.defaultTemplate } : p));
  return promptsMem.find((p) => p.id === id)!;
}

// ---------------- Render ----------------
let renderSettingsMem = { ...defaultRenderSettings };
export async function getRenderSettings(): Promise<RenderSettings> {
  await sleep(80);
  return renderSettingsMem;
}
export async function saveRenderSettings(s: RenderSettings) {
  await sleep(120);
  renderSettingsMem = s;
  return s;
}

export function startRender(
  _projectId: string,
  _settings: RenderSettings,
  onEvent: (job: RenderJob) => void,
): () => void {
  let progress = 0;
  const id = `r${Date.now()}`;
  const interval = setInterval(() => {
    progress = Math.min(1, progress + 0.06 + Math.random() * 0.04);
    if (progress >= 1) {
      clearInterval(interval);
      onEvent({
        id,
        status: "done",
        progress: 1,
        outputUrl:
          "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
      });
    } else {
      onEvent({ id, status: "running", progress });
    }
  }, 500);
  onEvent({ id, status: "running", progress: 0 });
  return () => clearInterval(interval);
}

// ---------------- Visual type schemas ----------------
// Drives the schema-driven params form in the editor inspector.
export interface ParamField {
  key: string;
  label: string;
  kind: "text" | "textarea" | "number" | "list" | "bars";
  placeholder?: string;
}

export const visualTypeSchemas: Record<
  string,
  { label: string; description: string; fields: ParamField[] }
> = {
  "title.card": {
    label: "Title card",
    description: "Opening title with subtitle.",
    fields: [
      { key: "title", label: "Title", kind: "text" },
      { key: "subtitle", label: "Subtitle", kind: "text" },
    ],
  },
  "bullet.reveal": {
    label: "Bullet reveal",
    description: "Bullets revealed one at a time.",
    fields: [{ key: "bullets", label: "Bullets (one per line)", kind: "list" }],
  },
  "figure.callout": {
    label: "Figure callout",
    description: "Highlight a figure from the paper.",
    fields: [
      { key: "caption", label: "Caption", kind: "text" },
      { key: "figureRef", label: "Figure reference", kind: "text", placeholder: "e.g. Fig. 3" },
    ],
  },
  "equation.build": {
    label: "Equation build",
    description: "Progressive equation reveal.",
    fields: [
      {
        key: "latex",
        label: "LaTeX",
        kind: "textarea",
        placeholder: "\\text{softmax}(QK^T/\\sqrt{d_k})V",
      },
    ],
  },
  "dataviz.bar": {
    label: "Bar chart",
    description: "Simple comparison bars.",
    fields: [{ key: "series", label: "Series (label,value per line)", kind: "bars" }],
  },
  "diagram.attention": {
    label: "Attention diagram",
    description: "Token-to-token attention lines.",
    fields: [{ key: "tokens", label: "Tokens (one per line)", kind: "list" }],
  },
  "comparison.split": {
    label: "Comparison split",
    description: "Side-by-side comparison.",
    fields: [
      { key: "left", label: "Left", kind: "text" },
      { key: "right", label: "Right", kind: "text" },
    ],
  },
  "kinetic.type": {
    label: "Kinetic typography",
    description: "Animated single-word emphasis.",
    fields: [{ key: "text", label: "Text", kind: "text" }],
  },
};
