import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  HelpCircle,
  Info,
  KeyRound,
  Loader2,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react";
import {
  addConnection,
  listAssignments,
  listConnections,
  removeConnection,
  testConnection,
  testConnectionDraft,
  updateAssignment,
} from "@/services/api";
import type {
  ConnectionTestResult,
  ProviderConnection,
  ProviderId,
  ProviderKind,
} from "@/services/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";

export const Route = createFileRoute("/model-config")({
  component: ModelConfigPage,
});

// Curated model lists (current as of 2026-07). `keyless` providers run locally
// or built-in and need no API key. LLM providers drive the reasoning/vision
// agents; TTS providers drive the narrator. Users can still edit a connection's
// model string if they need one not listed.
type ProviderMeta = {
  id: ProviderId;
  label: string;
  kind: ProviderKind;
  keyless?: boolean;
  models: string[];
};

const PROVIDERS: ProviderMeta[] = [
  // ── LLM — agent reasoning + vision ──────────────────────────────────────
  { id: "openai", label: "OpenAI", kind: "llm", models: ["gpt-5.5", "gpt-5.4", "o3", "o4-mini"] },
  {
    id: "anthropic",
    label: "Anthropic",
    kind: "llm",
    models: ["claude-fable-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
  },
  {
    id: "gemini",
    label: "Google Gemini",
    kind: "llm",
    models: ["gemini-3.5-flash", "gemini-3.1-pro", "gemini-3.1-flash-lite"],
  },
  {
    id: "groq",
    label: "Groq",
    kind: "llm",
    models: [
      "llama-3.3-70b-versatile",
      "openai/gpt-oss-120b",
      "openai/gpt-oss-20b",
      "moonshotai/kimi-k2-instruct",
      "deepseek-r1-distill-llama-70b",
    ],
  },
  {
    id: "ollama",
    label: "Ollama (local)",
    kind: "llm",
    keyless: true,
    models: ["qwen3:30b", "qwen3-coder:30b", "deepseek-r1:32b", "gemma3:27b", "gpt-oss:20b"],
  },
  // ── TTS — narration ─────────────────────────────────────────────────────
  {
    id: "hyperframes",
    label: "HyperFrames (built-in)",
    kind: "tts",
    keyless: true,
    models: ["builtin"],
  },
  {
    id: "elevenlabs",
    label: "ElevenLabs",
    kind: "tts",
    models: ["eleven_v3", "eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5"],
  },
  {
    id: "deepgram",
    label: "Deepgram",
    kind: "tts",
    models: ["aura-2-thalia-en", "aura-2-helena-en", "aura-2-orion-en", "aura-asteria-en"],
  },
];

const LLM_PROVIDERS = PROVIDERS.filter((p) => p.kind === "llm");
const TTS_PROVIDERS = PROVIDERS.filter((p) => p.kind === "tts");
const PROVIDER_KIND: Record<ProviderId, ProviderKind> = Object.fromEntries(
  PROVIDERS.map((p) => [p.id, p.kind]),
) as Record<ProviderId, ProviderKind>;

const ROLES: {
  id: "comprehension" | "planner" | "scriptwriter" | "visual_designer" | "narrator" | "verifier";
  label: string;
  hint: string;
}[] = [
  {
    id: "comprehension",
    label: "Comprehension",
    hint: "Reads the document and structures its argument",
  },
  { id: "planner", label: "Planner", hint: "Turns comprehension into scene beats" },
  { id: "scriptwriter", label: "Scriptwriter", hint: "Writes narration for each scene" },
  { id: "visual_designer", label: "Visual Designer", hint: "Picks visual types and parameters" },
  { id: "narrator", label: "Narrator (TTS)", hint: "Speaks the narration" },
  { id: "verifier", label: "Verifier", hint: "Checks every claim against the document" },
];

function StatusPill({ status }: { status: ProviderConnection["status"] }) {
  if (status === "ok")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-[color:var(--success)]">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Connected
      </span>
    );
  if (status === "error")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive">
        <XCircle className="h-3.5 w-3.5" />
        Failed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <HelpCircle className="h-3.5 w-3.5" />
      Untested
    </span>
  );
}

function AddConnectionForm({ onDone }: { onDone: () => void }) {
  const [provider, setProvider] = useState<ProviderId>("openai");
  const [model, setModel] = useState(LLM_PROVIDERS[0].models[0]);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      addConnection({
        provider,
        model,
        apiKey,
        baseUrl: baseUrl || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      toast.success("Connection added");
      onDone();
    },
  });
  const testMutation = useMutation({
    mutationFn: () =>
      testConnectionDraft({ provider, model, apiKey, baseUrl: baseUrl || undefined }),
    onSuccess: (r) => {
      setTestResult(r);
      if (r.success) toast.success(`Connection OK (${r.latencyMs}ms)`);
      else toast.error(r.error ?? "Connection failed");
    },
  });
  const providerMeta = PROVIDERS.find((p) => p.id === provider);
  const providerModels = providerMeta?.models ?? [];
  const keyless = providerMeta?.keyless ?? false;
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 text-sm font-semibold">Add connection</div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Provider</Label>
          <Select
            value={provider}
            onValueChange={(v) => {
              setProvider(v as ProviderId);
              const first = PROVIDERS.find((p) => p.id === v)?.models[0];
              if (first) setModel(first);
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>LLM (agents)</SelectLabel>
                {LLM_PROVIDERS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectGroup>
              <SelectGroup>
                <SelectLabel>TTS (narration)</SelectLabel>
                {TTS_PROVIDERS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>{providerMeta?.kind === "tts" ? "Voice / model" : "Model"}</Label>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {providerModels.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!keyless && (
          <>
            <div className="space-y-1">
              <Label>API key</Label>
              <Input
                type="password"
                placeholder="sk-…"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label>
                Base URL <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                placeholder="https://api.example.com"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </div>
          </>
        )}
        {keyless && (
          <div className="col-span-2 self-end text-xs text-muted-foreground">
            {provider === "ollama"
              ? "Local provider — no API key needed. Set Base URL via OLLAMA_HOST if not default."
              : "Built-in provider — no API key needed."}
          </div>
        )}
      </div>
      {testResult && (
        <div
          className={
            "mt-3 flex items-center gap-2 rounded-md border px-3 py-2 text-xs " +
            (testResult.success
              ? "border-[color:var(--success)]/40 text-[color:var(--success)]"
              : "border-destructive/40 text-destructive")
          }
        >
          {testResult.success ? (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <XCircle className="h-3.5 w-3.5 shrink-0" />
          )}
          <span className="break-all">
            {testResult.success
              ? `Connected in ${testResult.latencyMs}ms${testResult.detail ? ` · ${testResult.detail}` : ""}`
              : (testResult.error ?? "Connection failed")}
          </span>
        </div>
      )}
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button
          variant="outline"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Test"}
        </Button>
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          Add
        </Button>
      </div>
    </div>
  );
}

function ModelConfigPage() {
  const [adding, setAdding] = useState(false);
  const qc = useQueryClient();
  const { data: connections = [] } = useQuery({
    queryKey: ["connections"],
    queryFn: listConnections,
  });
  const { data: assignments = [] } = useQuery({
    queryKey: ["assignments"],
    queryFn: listAssignments,
  });

  const testMut = useMutation({
    mutationFn: (id: string) => testConnection(id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      if (r.success) toast.success(`Connection OK (${r.latencyMs}ms)`);
      else toast.error(r.error ?? "Connection failed");
    },
  });
  const removeMut = useMutation({
    mutationFn: (id: string) => removeConnection(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      qc.invalidateQueries({ queryKey: ["assignments"] });
    },
  });
  const assignMut = useMutation({
    mutationFn: ({
      role,
      connectionId,
    }: {
      role: (typeof ROLES)[number]["id"];
      connectionId: string | null;
    }) => updateAssignment(role, connectionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assignments"] }),
  });

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Model configuration</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Provider connections and per-agent model assignments.
          </p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add connection
          </Button>
        )}
      </div>

      <Alert className="mb-6 border-border bg-card">
        <Info className="h-4 w-4" />
        <AlertDescription className="text-xs text-muted-foreground">
          API keys are stored encrypted on your server. Vyakhya never sends them anywhere except the
          provider you configure.
        </AlertDescription>
      </Alert>

      {adding && (
        <div className="mb-6">
          <AddConnectionForm onDone={() => setAdding(false)} />
        </div>
      )}

      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Provider connections
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Provider</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Key</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-0" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {connections.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium capitalize">{c.provider}</TableCell>
                <TableCell className="text-muted-foreground">{c.model}</TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-1 font-mono text-xs">
                    <KeyRound className="h-3 w-3" />
                    {c.apiKeyMasked}
                  </span>
                </TableCell>
                <TableCell>
                  <StatusPill status={c.status} />
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => testMut.mutate(c.id)}
                      disabled={testMut.isPending}
                    >
                      {testMut.isPending && testMut.variables === c.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        "Test"
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => removeMut.mutate(c.id)}
                      aria-label="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="mt-8 rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3 text-sm font-semibold">
          Agent role assignments
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Agent role</TableHead>
              <TableHead>Connection</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROLES.map((r) => {
              const a = assignments.find((x) => x.role === r.id);
              // The narrator is voiced by a TTS provider; every other agent is
              // driven by an LLM. Only offer connections of the matching kind.
              const roleKind: ProviderKind = r.id === "narrator" ? "tts" : "llm";
              const eligible = connections.filter((c) => PROVIDER_KIND[c.provider] === roleKind);
              return (
                <TableRow key={r.id}>
                  <TableCell>
                    <div className="font-medium">{r.label}</div>
                    <div className="text-[11px] text-muted-foreground">{r.hint}</div>
                  </TableCell>
                  <TableCell>
                    <Select
                      value={a?.connectionId ?? "none"}
                      onValueChange={(v) =>
                        assignMut.mutate({ role: r.id, connectionId: v === "none" ? null : v })
                      }
                    >
                      <SelectTrigger className="w-72">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">— unassigned —</SelectItem>
                        {eligible.map((c) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.provider} · {c.model}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
