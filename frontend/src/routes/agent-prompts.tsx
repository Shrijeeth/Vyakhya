import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import Editor from "@monaco-editor/react";
import { toast } from "sonner";
import { RotateCcw, GitCompareArrows, Save } from "lucide-react";
import { listPrompts, resetPrompt, savePrompt } from "@/services/api";
import type { AgentId } from "@/services/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

export const Route = createFileRoute("/agent-prompts")({
  component: AgentPromptsPage,
});

function AgentPromptsPage() {
  const qc = useQueryClient();
  const { data: prompts = [] } = useQuery({ queryKey: ["prompts"], queryFn: listPrompts });
  const [selected, setSelected] = useState<AgentId | null>(null);
  const [draft, setDraft] = useState("");
  const [diffOpen, setDiffOpen] = useState(false);
  const active = prompts.find((p) => p.id === selected) ?? prompts[0];

  useEffect(() => {
    if (active) {
      setSelected(active.id);
      setDraft(active.template);
    }
  }, [active?.id]); // eslint-disable-line

  const saveMut = useMutation({
    mutationFn: () => savePrompt(active!.id, draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prompts"] });
      toast.success("Prompt saved");
    },
  });
  const resetMut = useMutation({
    mutationFn: () => resetPrompt(active!.id),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["prompts"] });
      setDraft(p.template);
      toast.success("Reset to default");
    },
  });

  if (!active) return null;
  const dirty = draft !== active.template;

  return (
    <div className="mx-auto flex h-full max-w-7xl gap-6 px-8 py-8">
      <aside className="w-64 shrink-0">
        <h1 className="text-2xl font-semibold tracking-tight">Agent prompts</h1>
        <p className="mt-1 text-xs text-muted-foreground">Tune how each agent thinks.</p>
        <ul className="mt-6 space-y-1">
          {prompts.map((p) => (
            <li key={p.id}>
              <button
                onClick={() => {
                  setSelected(p.id);
                  setDraft(p.template);
                }}
                className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  p.id === active.id
                    ? "bg-accent text-accent-foreground font-medium"
                    : "hover:bg-muted/60"
                }`}
              >
                {p.label}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div>
            <div className="text-sm font-semibold">{active.label}</div>
            <div className="text-[11px] text-muted-foreground">Prompt template</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setDiffOpen(true)}>
              <GitCompareArrows className="mr-1.5 h-3.5 w-3.5" />
              Diff vs default
            </Button>
            <Button variant="ghost" size="sm" onClick={() => resetMut.mutate()}>
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              Reset
            </Button>
            <Button
              size="sm"
              onClick={() => saveMut.mutate()}
              disabled={!dirty || saveMut.isPending}
            >
              <Save className="mr-1.5 h-3.5 w-3.5" />
              Save
            </Button>
          </div>
        </div>

        <div className="mt-4 grid min-h-0 flex-1 grid-cols-[1fr_260px] gap-4">
          <div className="overflow-hidden rounded-md border border-border bg-card">
            <Editor
              height="100%"
              defaultLanguage="markdown"
              theme={
                typeof window !== "undefined" && document.documentElement.classList.contains("dark")
                  ? "vs-dark"
                  : "light"
              }
              value={draft}
              onChange={(v) => setDraft(v ?? "")}
              options={{
                minimap: { enabled: false },
                wordWrap: "on",
                fontSize: 13,
                scrollBeyondLastLine: false,
                padding: { top: 12, bottom: 12 },
              }}
            />
          </div>
          <div className="rounded-md border border-border bg-card">
            <div className="border-b border-border px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Variables
            </div>
            <ScrollArea className="h-[calc(100%-32px)]">
              <ul className="space-y-1 p-3">
                {active.variables.map((v) => (
                  <li key={v.name} className="rounded-md border border-border bg-muted/30 p-2">
                    <div className="font-mono text-[11px] text-primary">{`{{${v.name}}}`}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">{v.description}</div>
                  </li>
                ))}
              </ul>
            </ScrollArea>
          </div>
        </div>
      </div>

      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Diff against default — {active.label}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase text-muted-foreground">
                Default
              </div>
              <pre className="max-h-[420px] overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
                {active.defaultTemplate}
              </pre>
            </div>
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase text-muted-foreground">
                Current
              </div>
              <pre className="max-h-[420px] overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
                {draft}
              </pre>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
