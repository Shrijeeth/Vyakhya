// Shared domain types for the Vyakhya frontend.
// Backend contracts land here so screens code against types, not fetch calls.

export type ProjectStatus = "draft" | "generating" | "ready" | "failed";
export type AudienceLevel = "layperson" | "student" | "expert";
export type AspectRatio = "16:9" | "9:16" | "1:1";

export interface Project {
  id: string;
  title: string;
  sourcePaper: string;
  thumbnail?: string;
  status: ProjectStatus;
  durationMs: number;
  updatedAt: string;
  audience: AudienceLevel;
  aspectRatio: AspectRatio;
  language: string;
  ttsEnabled: boolean;
}

export type AgentId =
  | "ingestor"
  | "comprehension"
  | "planner"
  | "scriptwriter"
  | "visual_designer"
  | "narrator"
  | "verifier"
  | "assembler";

export type AgentStatus = "queued" | "running" | "done" | "error";

export interface AgentNodeState {
  id: AgentId;
  label: string;
  status: AgentStatus;
  elapsedMs: number;
  logs: string[];
  result?: unknown;
}

export interface VerifierFlag {
  id: string;
  claim: string;
  sourceSpan: string;
  level: "pass" | "warn" | "fail";
  note?: string;
}

export interface PipelineEvent {
  type: "status" | "log" | "flag" | "scenes" | "progress" | "error" | "done";
  agentId?: AgentId;
  payload: unknown;
}

export type VisualType =
  | "title.card"
  | "bullet.reveal"
  | "figure.callout"
  | "equation.build"
  | "dataviz.bar"
  | "diagram.attention"
  | "comparison.split"
  | "kinetic.type";

export interface SceneCitation {
  id: string;
  label: string;
  sourceSpan: string;
}

export interface Scene {
  id: string;
  index: number;
  narration: string;
  visualType: VisualType;
  params: Record<string, unknown>;
  captionStyle: "none" | "minimal" | "bold";
  transition: "cut" | "fade" | "slide" | "wipe";
  durationMs: number | "auto";
  citations: SceneCitation[];
}

export interface EditorProject {
  id: string;
  title: string;
  scenes: Scene[];
  totalDurationMs: number;
  aspectRatio: AspectRatio;
}

// LLM providers (agent reasoning + vision) and TTS providers (narration).
export type ProviderId =
  "openai" | "anthropic" | "gemini" | "groq" | "ollama" | "hyperframes" | "elevenlabs" | "deepgram";

export type ProviderKind = "llm" | "tts";

export interface ProviderConnection {
  id: string;
  provider: ProviderId;
  kind: ProviderKind; // derived from provider (llm | tts)
  model: string;
  apiKeyMasked: string;
  baseUrl?: string;
  status: "unknown" | "ok" | "error";
  settings?: Record<string, unknown>; // kind-specific tuning
  lastTestedAt?: string;
}

export interface ConnectionTestResult {
  success: boolean;
  latencyMs: number;
  detail?: string;
  error?: string;
}

export type AgentRole =
  "comprehension" | "planner" | "scriptwriter" | "visual_designer" | "narrator" | "verifier";

export interface AgentModelAssignment {
  role: AgentRole;
  connectionId: string | null;
}

export interface AgentPrompt {
  id: AgentId;
  label: string;
  template: string;
  defaultTemplate: string;
  variables: { name: string; description: string }[];
}

export interface RenderJob {
  id: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  outputUrl?: string | null;
  error?: string | null;
  createdAt?: string | null;
  finishedAt?: string | null;
}

export interface RenderSettings {
  fps: 24 | 30 | 60;
  width: number;
  height: number;
  quality: number; // 0-100
  format: "mp4" | "webm";
  codec: "h264" | "h265" | "vp9" | "av1";
  gpu: boolean;
  workers: number;
  audioMasterDb: number;
  audioNarrationDb: number;
  audioMusicDb: number;
}
