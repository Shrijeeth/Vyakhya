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
  updateAssignment,
} from "@/services/api";
import type { ProviderConnection, ProviderId } from "@/services/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
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

const PROVIDERS: { id: ProviderId; label: string; models: string[] }[] = [
  { id: "openai", label: "OpenAI", models: ["gpt-4o", "gpt-4o-mini", "o1-preview"] },
  {
    id: "anthropic",
    label: "Anthropic",
    models: ["claude-3.5-sonnet", "claude-3.5-haiku", "claude-3-opus"],
  },
  { id: "gemini", label: "Google Gemini", models: ["gemini-2.0-flash", "gemini-1.5-pro"] },
  { id: "groq", label: "Groq", models: ["llama-3.1-70b", "mixtral-8x7b"] },
  { id: "elevenlabs", label: "ElevenLabs", models: ["eleven_multilingual_v2", "eleven_turbo_v2"] },
  { id: "ollama", label: "Ollama (local)", models: ["llama3.1:70b", "qwen2.5:32b", "mistral"] },
];

const ROLES: {
  id: "comprehension" | "planner" | "scriptwriter" | "visual_designer" | "narrator" | "verifier";
  label: string;
  hint: string;
}[] = [
  {
    id: "comprehension",
    label: "Comprehension",
    hint: "Reads the paper and structures its argument",
  },
  { id: "planner", label: "Planner", hint: "Turns comprehension into scene beats" },
  { id: "scriptwriter", label: "Scriptwriter", hint: "Writes narration for each scene" },
  { id: "visual_designer", label: "Visual Designer", hint: "Picks visual types and parameters" },
  { id: "narrator", label: "Narrator (TTS)", hint: "Speaks the narration" },
  { id: "verifier", label: "Verifier", hint: "Checks every claim against the paper" },
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
  const [model, setModel] = useState("gpt-4o");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      addConnection({
        provider,
        model,
        apiKeyMasked: apiKey ? `${apiKey.slice(0, 3)}…${apiKey.slice(-4)}` : "—",
        baseUrl: baseUrl || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      toast.success("Connection added");
      onDone();
    },
  });
  const providerModels = PROVIDERS.find((p) => p.id === provider)?.models ?? [];
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
              {PROVIDERS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Model</Label>
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
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      toast.success("Connection ok");
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
                        {connections.map((c) => (
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
