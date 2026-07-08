import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, Handle, Position } from "@xyflow/react";
import type { Edge, Node, NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  CheckCircle2,
  Loader2,
  Circle,
  AlertTriangle,
  X,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
} from "lucide-react";
import { getAgentSequence, subscribePipeline } from "@/services/api";
import type { AgentId, AgentStatus, VerifierFlag } from "@/services/types";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

export const Route = createFileRoute("/projects/$projectId/pipeline")({
  component: PipelinePage,
});

type AgentNode = {
  id: AgentId;
  label: string;
  status: AgentStatus;
  startedAt?: number;
  elapsedMs: number;
  logs: string[];
};

function AgentFlowNode({ data }: NodeProps<Node<AgentNode>>) {
  const s = data.status;
  const Icon =
    s === "done"
      ? CheckCircle2
      : s === "running"
        ? Loader2
        : s === "error"
          ? AlertTriangle
          : Circle;
  const color =
    s === "done"
      ? "text-[color:var(--success)] border-[color:var(--success)]/40 bg-[color:var(--success)]/5"
      : s === "running"
        ? "text-primary border-primary/40 bg-accent"
        : s === "error"
          ? "text-destructive border-destructive/40 bg-destructive/5"
          : "text-muted-foreground border-border bg-card";
  return (
    <div className={`min-w-[168px] rounded-lg border px-3.5 py-3 shadow-sm ${color}`}>
      <Handle type="target" position={Position.Left} className="!bg-border" />
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${s === "running" ? "animate-spin" : ""}`} />
        <div className="text-sm font-medium text-foreground">{data.label}</div>
      </div>
      <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
        <span className="capitalize">{s}</span>
        <span>{(data.elapsedMs / 1000).toFixed(1)}s</span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-border" />
    </div>
  );
}

const nodeTypes = { agent: AgentFlowNode };

function LevelIcon({ level }: { level: VerifierFlag["level"] }) {
  if (level === "pass") return <ShieldCheck className="h-4 w-4 text-[color:var(--success)]" />;
  if (level === "warn") return <ShieldQuestion className="h-4 w-4 text-[color:var(--warning)]" />;
  return <ShieldAlert className="h-4 w-4 text-destructive" />;
}

function PipelinePage() {
  const { projectId } = Route.useParams();
  const navigate = useNavigate();
  const sequence = useMemo(() => getAgentSequence(), []);
  const [agents, setAgents] = useState<AgentNode[]>(() =>
    sequence.map((a) => ({ ...a, status: "queued" as AgentStatus, elapsedMs: 0, logs: [] })),
  );
  const [progress, setProgress] = useState(0);
  const [selected, setSelected] = useState<AgentId | null>(null);
  const [flags, setFlags] = useState<VerifierFlag[]>([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // tick elapsed for running agents
    const t = setInterval(() => {
      setAgents((prev) =>
        prev.map((a) => (a.status === "running" ? { ...a, elapsedMs: a.elapsedMs + 100 } : a)),
      );
    }, 100);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const unsub = subscribePipeline(projectId, (evt) => {
      if (evt.type === "status" && evt.agentId) {
        setAgents((prev) =>
          prev.map((a) =>
            a.id === evt.agentId ? { ...a, status: evt.payload as AgentStatus } : a,
          ),
        );
      } else if (evt.type === "log" && evt.agentId) {
        setAgents((prev) =>
          prev.map((a) =>
            a.id === evt.agentId ? { ...a, logs: [...a.logs, String(evt.payload)] } : a,
          ),
        );
      } else if (evt.type === "flag") {
        setFlags((prev) => [...prev, evt.payload as VerifierFlag]);
      } else if (evt.type === "progress") {
        setProgress(Number(evt.payload) * 100);
      } else if (evt.type === "done") {
        setDone(true);
      }
    });
    return unsub;
  }, [projectId]);

  const nodes: Node<AgentNode>[] = agents.map((a, i) => ({
    id: a.id,
    type: "agent",
    data: a,
    position: { x: i * 220, y: 40 },
  }));
  const edges: Edge[] = agents.slice(1).map((a, i) => ({
    id: `${agents[i].id}-${a.id}`,
    source: agents[i].id,
    target: a.id,
    animated: agents[i].status === "done" && a.status !== "queued",
    style: { stroke: "var(--color-border)" },
  }));

  const active = agents.find((a) => a.id === selected);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border bg-card/40 px-8 py-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold">Generation pipeline</h1>
            <p className="text-xs text-muted-foreground">
              Live view of the agent crew turning the paper into an editable video.
            </p>
          </div>
          <Button
            disabled={!done}
            onClick={() => navigate({ to: "/projects/$projectId/editor", params: { projectId } })}
          >
            Open in editor
          </Button>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Progress value={progress} className="h-1.5 flex-1" />
          <span className="text-xs tabular-nums text-muted-foreground">
            {Math.round(progress)}%
          </span>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 border-r border-border" style={{ background: "var(--color-muted)" }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_, n) => setSelected(n.id as AgentId)}
            nodesDraggable={false}
            nodesConnectable={false}
          >
            <Background gap={20} color="var(--color-border)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <aside className="w-[420px] shrink-0 overflow-hidden">
          {active ? (
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-border px-5 py-3">
                <div>
                  <div className="text-sm font-semibold">{active.label}</div>
                  <div className="text-[11px] capitalize text-muted-foreground">
                    {active.status}
                  </div>
                </div>
                <button
                  onClick={() => setSelected(null)}
                  className="rounded p-1 text-muted-foreground hover:bg-muted"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <ScrollArea className="flex-1">
                <div className="space-y-4 px-5 py-4">
                  <div>
                    <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      Streaming log
                    </div>
                    <pre className="max-h-64 overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed text-foreground/80">
                      {active.logs.length ? active.logs.join("\n") : "…waiting"}
                    </pre>
                  </div>
                  <Collapsible>
                    <CollapsibleTrigger className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground">
                      Structured result
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed text-foreground/80">
                        {active.status === "done"
                          ? JSON.stringify(
                              { agent: active.id, ok: true, itemsProduced: 12 },
                              null,
                              2,
                            )
                          : "// available when the agent completes"}
                      </pre>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              </ScrollArea>
            </div>
          ) : (
            <div className="flex h-full flex-col">
              <div className="border-b border-border px-5 py-3">
                <div className="text-sm font-semibold">Verifier flags</div>
                <div className="text-[11px] text-muted-foreground">
                  Every claim in the narration, checked against the paper.
                </div>
              </div>
              <ScrollArea className="flex-1">
                <div className="space-y-2 px-5 py-4">
                  {flags.length === 0 ? (
                    <div className="rounded-md border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
                      Verifier hasn't reported yet.
                    </div>
                  ) : (
                    flags.map((f) => (
                      <div key={f.id} className="rounded-md border border-border bg-card p-3">
                        <div className="flex items-start gap-2">
                          <LevelIcon level={f.level} />
                          <div className="flex-1">
                            <div className="text-xs leading-snug">{f.claim}</div>
                            <div className="mt-1 text-[11px] text-muted-foreground">
                              {f.sourceSpan}
                            </div>
                            {f.note && (
                              <div className="mt-1 text-[11px] text-[color:var(--warning)]">
                                {f.note}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
