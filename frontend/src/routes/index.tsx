import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, FileText, Clock, AlertTriangle, CheckCircle2, Loader2, FilePlus2 } from "lucide-react";
import { listProjects } from "@/services/api";
import type { Project, ProjectStatus } from "@/services/types";
import { Button } from "@/components/ui/button";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";

export const Route = createFileRoute("/")({
  component: ProjectsPage,
});

const STATUS_STYLES: Record<ProjectStatus, { label: string; className: string; icon: React.ComponentType<{ className?: string }> }> = {
  draft: { label: "Draft", className: "bg-muted text-muted-foreground", icon: FileText },
  generating: { label: "Generating", className: "bg-accent text-accent-foreground", icon: Loader2 },
  ready: { label: "Ready", className: "bg-[color:var(--success)]/15 text-[color:var(--success)]", icon: CheckCircle2 },
  failed: { label: "Failed", className: "bg-destructive/15 text-destructive", icon: AlertTriangle },
};

function formatDuration(ms: number) {
  if (!ms) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatUpdated(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ProjectCard({ project, onOpen }: { project: Project; onOpen: (p: Project) => void }) {
  const style = STATUS_STYLES[project.status];
  const Icon = style.icon;
  return (
    <button
      onClick={() => onOpen(project)}
      className="group flex flex-col overflow-hidden rounded-lg border border-border bg-card text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="relative aspect-[16/9] w-full overflow-hidden bg-gradient-to-br from-accent via-muted to-secondary">
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-devanagari text-6xl text-primary/25">व्या</span>
        </div>
        <div className="absolute right-3 top-3">
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}>
            <Icon className={`h-3 w-3 ${project.status === "generating" ? "animate-spin" : ""}`} />
            {style.label}
          </span>
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="line-clamp-2 font-medium leading-tight">{project.title}</h3>
        <p className="text-xs text-muted-foreground">{project.sourcePaper}</p>
        <div className="mt-auto flex items-center justify-between pt-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{formatDuration(project.durationMs)}</span>
          <span>{formatUpdated(project.updatedAt)}</span>
        </div>
      </div>
    </button>
  );
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="mx-auto max-w-md rounded-lg border border-dashed border-border bg-card/50 p-12 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <FilePlus2 className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold">Explain your first paper</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Upload a PDF and Vyakhya's agent crew will draft a full, editable explainer video — narration, visuals, and citations included.
      </p>
      <Button className="mt-6" onClick={onNew}>
        <Plus className="mr-1.5 h-4 w-4" /> New video
      </Button>
    </div>
  );
}

function ProjectsPage() {
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data: projects, isLoading } = useQuery({ queryKey: ["projects"], queryFn: listProjects });

  const openProject = (p: Project) => {
    if (p.status === "ready" || p.status === "draft") {
      navigate({ to: "/projects/$projectId/editor", params: { projectId: p.id } });
    } else {
      navigate({ to: "/projects/$projectId/pipeline", params: { projectId: p.id } });
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every paper you've explained, in one place.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> New video
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-lg border border-border bg-card/50" />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} onOpen={openProject} />
          ))}
        </div>
      ) : (
        <EmptyState onNew={() => setDialogOpen(true)} />
      )}

      <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
