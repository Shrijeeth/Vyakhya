import type {
  AgentPrompt,
  AgentModelAssignment,
  EditorProject,
  Project,
  ProviderConnection,
  RenderSettings,
  Scene,
  VerifierFlag,
  VisualType,
} from "./types";

export const mockProjects: Project[] = [
  {
    id: "p1",
    title: "Attention Is All You Need — Explained",
    sourcePaper: "Vaswani et al., 2017",
    status: "ready",
    durationMs: 5 * 60 * 1000 + 42_000,
    updatedAt: "2026-07-05T10:24:00Z",
    audience: "student",
    aspectRatio: "16:9",
    language: "en",
  },
  {
    id: "p2",
    title: "AlphaFold 2 for the Curious",
    sourcePaper: "Jumper et al., 2021",
    status: "generating",
    durationMs: 0,
    updatedAt: "2026-07-07T08:12:00Z",
    audience: "layperson",
    aspectRatio: "16:9",
    language: "en",
  },
  {
    id: "p3",
    title: "Diffusion Models: A Visual Primer",
    sourcePaper: "Ho et al., 2020",
    status: "draft",
    durationMs: 0,
    updatedAt: "2026-07-04T18:03:00Z",
    audience: "expert",
    aspectRatio: "9:16",
    language: "en",
  },
  {
    id: "p4",
    title: "CLIP: Learning Transferable Visual Models",
    sourcePaper: "Radford et al., 2021",
    status: "failed",
    durationMs: 0,
    updatedAt: "2026-07-02T14:41:00Z",
    audience: "student",
    aspectRatio: "1:1",
    language: "en",
  },
];

export const mockVerifierFlags: VerifierFlag[] = [
  {
    id: "vf1",
    claim: "Self-attention has O(n²) complexity in sequence length.",
    sourceSpan: "§3.2, p. 4, ¶ 2",
    level: "pass",
  },
  {
    id: "vf2",
    claim: "Transformer trained in 12 hours on 8 P100 GPUs.",
    sourceSpan: "§5.1, p. 7",
    level: "warn",
    note: "Paper reports 12h for base model; large model took 3.5 days.",
  },
  {
    id: "vf3",
    claim: "BLEU score of 28.4 on WMT 2014 EN-DE.",
    sourceSpan: "Table 2",
    level: "pass",
  },
  {
    id: "vf4",
    claim: "Positional encodings are learned, not fixed.",
    sourceSpan: "§3.5",
    level: "fail",
    note: "Paper uses fixed sinusoidal encodings for the base configuration.",
  },
];

const s = (
  i: number,
  narration: string,
  visualType: VisualType,
  params: Record<string, unknown> = {},
  durationMs = 8000,
): Scene => ({
  id: `s${i}`,
  index: i,
  narration,
  visualType,
  params,
  captionStyle: "minimal",
  transition: "fade",
  durationMs,
  citations: [{ id: `c${i}`, label: `[${i}]`, sourceSpan: `§${i}.1, p. ${i + 2}` }],
});

export const mockEditorProject: EditorProject = {
  id: "p1",
  title: "Attention Is All You Need — Explained",
  aspectRatio: "16:9",
  totalDurationMs: 5 * 60 * 1000 + 42_000,
  scenes: [
    s(
      1,
      "In 2017, a team at Google published a paper that quietly rewrote how machines understand language.",
      "title.card",
      { title: "Attention Is All You Need", subtitle: "Vaswani et al., 2017" },
      6000,
    ),
    s(
      2,
      "Before the Transformer, sequence models processed words one at a time. This was slow, and it forgot long-range context.",
      "bullet.reveal",
      { bullets: ["Sequential processing", "Vanishing context", "Hard to parallelize"] },
      9000,
    ),
    s(
      3,
      "The Transformer replaces recurrence with a single mechanism: attention.",
      "kinetic.type",
      { text: "attention" },
      5000,
    ),
    s(
      4,
      "Attention scores every pair of tokens, letting the model weigh what matters, everywhere at once.",
      "diagram.attention",
      { tokens: ["The", "cat", "sat", "on", "the", "mat"] },
      10000,
    ),
    s(
      5,
      "Multi-head attention runs several attention operations in parallel, each learning a different relationship.",
      "figure.callout",
      { caption: "Multi-Head Attention" },
      8000,
    ),
    s(
      6,
      "The whole architecture stacks encoder and decoder blocks — no recurrence, no convolution.",
      "comparison.split",
      { left: "RNN", right: "Transformer" },
      8000,
    ),
    s(
      7,
      "Training was faster, results were state of the art, and every modern LLM traces back to this design.",
      "dataviz.bar",
      {
        series: [
          { label: "RNN", value: 25.2 },
          { label: "Transformer", value: 28.4 },
        ],
      },
      8000,
    ),
  ],
};

export const mockConnections: ProviderConnection[] = [
  {
    id: "c1",
    provider: "openai",
    model: "gpt-4o",
    apiKeyMasked: "sk-…4a8f",
    status: "ok",
    lastTestedAt: "2026-07-06T09:00:00Z",
  },
  {
    id: "c2",
    provider: "anthropic",
    model: "claude-3.5-sonnet",
    apiKeyMasked: "sk-ant-…9b21",
    status: "ok",
    lastTestedAt: "2026-07-06T09:01:00Z",
  },
  {
    id: "c3",
    provider: "elevenlabs",
    model: "eleven_multilingual_v2",
    apiKeyMasked: "el-…7cc0",
    status: "ok",
  },
  {
    id: "c4",
    provider: "ollama",
    model: "llama3.1:70b",
    apiKeyMasked: "—",
    baseUrl: "http://localhost:11434",
    status: "unknown",
  },
];

export const mockAssignments: AgentModelAssignment[] = [
  { role: "comprehension", connectionId: "c2" },
  { role: "planner", connectionId: "c2" },
  { role: "scriptwriter", connectionId: "c1" },
  { role: "visual_designer", connectionId: "c1" },
  { role: "narrator", connectionId: "c3" },
  { role: "verifier", connectionId: "c2" },
];

export const mockPrompts: AgentPrompt[] = [
  {
    id: "comprehension",
    label: "Comprehension",
    template:
      "You are a research analyst. Read the paper below and produce a structured comprehension:\n- Core claim\n- Method\n- Key results\n- Limitations\n\nPaper:\n{{paper_text}}",
    defaultTemplate:
      "You are a research analyst. Read the paper below and produce a structured comprehension:\n- Core claim\n- Method\n- Key results\n- Limitations\n\nPaper:\n{{paper_text}}",
    variables: [
      { name: "paper_text", description: "Full parsed text of the paper" },
      { name: "audience", description: "Layperson | Student | Expert" },
    ],
  },
  {
    id: "planner",
    label: "Planner",
    template:
      "Given the comprehension, plan a {{target_length}} explainer for a {{audience}} audience. Output an ordered list of scene beats.\n\nComprehension:\n{{comprehension}}",
    defaultTemplate:
      "Given the comprehension, plan a {{target_length}} explainer for a {{audience}} audience. Output an ordered list of scene beats.\n\nComprehension:\n{{comprehension}}",
    variables: [
      { name: "comprehension", description: "Output of the Comprehension agent" },
      { name: "target_length", description: "Target video length hint" },
      { name: "audience", description: "Layperson | Student | Expert" },
    ],
  },
  {
    id: "scriptwriter",
    label: "Scriptwriter",
    template:
      "Write the narration for each scene beat. Voice: {{voice_style}}.\n\nBeats:\n{{beats}}",
    defaultTemplate:
      "Write the narration for each scene beat. Voice: {{voice_style}}.\n\nBeats:\n{{beats}}",
    variables: [
      { name: "beats", description: "Scene beats from Planner" },
      { name: "voice_style", description: "Narrative voice guidance" },
    ],
  },
  {
    id: "visual_designer",
    label: "Visual Designer",
    template:
      "For each scene, choose a visual type from the library and produce its parameters. Prefer figures cited by the paper when available.\n\nScenes:\n{{scenes}}\n\nFigures:\n{{figures}}",
    defaultTemplate:
      "For each scene, choose a visual type from the library and produce its parameters. Prefer figures cited by the paper when available.\n\nScenes:\n{{scenes}}\n\nFigures:\n{{figures}}",
    variables: [
      { name: "scenes", description: "Scene list with narration" },
      { name: "figures", description: "Extracted figures and tables" },
    ],
  },
  {
    id: "narrator",
    label: "Narrator (TTS)",
    template:
      "Voice: {{voice_id}}\nSpeed: {{speed}}\nStability: {{stability}}\n\nRender the following narration as audio, one file per scene.",
    defaultTemplate:
      "Voice: {{voice_id}}\nSpeed: {{speed}}\nStability: {{stability}}\n\nRender the following narration as audio, one file per scene.",
    variables: [
      { name: "voice_id", description: "TTS voice identifier" },
      { name: "speed", description: "Speaking rate multiplier" },
      { name: "stability", description: "Voice stability 0..1" },
    ],
  },
  {
    id: "verifier",
    label: "Verifier",
    template:
      "For every factual claim in the narration, locate its source span in the paper. Flag any claim not supported.\n\nNarration:\n{{narration}}\n\nPaper:\n{{paper_text}}",
    defaultTemplate:
      "For every factual claim in the narration, locate its source span in the paper. Flag any claim not supported.\n\nNarration:\n{{narration}}\n\nPaper:\n{{paper_text}}",
    variables: [
      { name: "narration", description: "Full narration text" },
      { name: "paper_text", description: "Full parsed paper text" },
    ],
  },
];

export const defaultRenderSettings: RenderSettings = {
  fps: 30,
  width: 1920,
  height: 1080,
  quality: 82,
  format: "mp4",
  codec: "h264",
  gpu: true,
  workers: 4,
  audioMasterDb: 0,
  audioNarrationDb: -2,
  audioMusicDb: -14,
};
