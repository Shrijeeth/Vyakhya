import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  FolderKanban,
  Clock,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  FileText,
  Sparkles,
  Plug,
  ShieldAlert,
} from "lucide-react";
import { listProjects, listConnections, getVerifierFlags } from "@/services/api";
import type { Project, ProjectStatus } from "@/services/types";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — Vyakhya" },
      { name: "description", content: "Overview of your Vyakhya workspace: projects, pipeline health, and recent activity." },
    ],
  }),
  component: DashboardPage,
});

const STATUS_META: Record<ProjectStatus, { label: string; className: string; icon: React.ComponentType<{ className?: string }> }> = {
  draft: { label: "Draft", className: "text-muted-foreground", icon: FileText },
  generating: { label: "Generating", className: "text-accent-foreground", icon: Loader2 },
  ready: { label: "Ready", className: "text-[color:var(--success)]", icon: CheckCircle2 },
  failed: { label: "Failed", className: "text-destructive", icon: AlertTriangle },
};

function formatDuration(ms: number) {
  if (!ms) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ComponentType<{ className?: string }>;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
        <Icon className={`h-4 w-4 ${accent ?? "text-muted-foreground"}`} />
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function DashboardPage() {
  const { data: projects = [], isLoading: projectsLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });
  const { data: connections = [] } = useQuery({
    queryKey: ["connections"],
    queryFn: listConnections,
  });
  const { data: flags = [] } = useQuery({
    queryKey: ["verifier-flags", "dashboard"],
    queryFn: () => getVerifierFlags("dashboard"),
  });

  const counts = projects.reduce(
    (acc, p) => {
      acc[p.status] += 1;
      return acc;
    },
    { draft: 0, generating: 0, ready: 0, failed: 0 } as Record<ProjectStatus, number>,
  );
  const totalDuration = projects.reduce((sum, p) => sum + (p.durationMs || 0), 0);
  const readyCount = counts.ready;
  const okConnections = connections.filter((c) => c.status === "ok").length;
  const failFlags = flags.filter((f) => f.level === "fail").length;
  const warnFlags = flags.filter((f) => f.level === "warn").length;

  const recent = [...projects]
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 6);

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A quick read on your workspace — projects, pipeline health, and recent activity.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total projects"
          value={projectsLoading ? "…" : projects.length}
          sub={`${readyCount} ready · ${counts.draft} draft`}
          icon={FolderKanban}
        />
        <StatCard
          label="Generating now"
          value={counts.generating}
          sub={counts.generating > 0 ? "Agents running" : "Idle"}
          icon={Sparkles}
          accent="text-accent-foreground"
        />
        <StatCard
          label="Total runtime"
          value={formatDuration(totalDuration)}
          sub="Across ready videos"
          icon={Clock}
        />
        <StatCard
          label="Provider health"
          value={`${okConnections}/${connections.length || 0}`}
          sub={okConnections === connections.length && connections.length > 0 ? "All keys OK" : "Some untested"}
          icon={Plug}
          accent={okConnections === connections.length && connections.length > 0 ? "text-[color:var(--success)]" : "text-muted-foreground"}
        />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h2 className="text-sm font-semibold">Recent projects</h2>
            <Link to="/" className="text-xs text-muted-foreground hover:text-foreground">
              View all →
            </Link>
          </div>
          {recent.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">No projects yet.</div>
          ) : (
            <ul className="divide-y divide-border">
              {recent.map((p) => {
                const meta = STATUS_META[p.status];
                const Icon = meta.icon;
                const to =
                  p.status === "ready" || p.status === "draft"
                    ? "/projects/$projectId/editor"
                    : "/projects/$projectId/pipeline";
                return (
                  <li key={p.id}>
                    <Link
                      to={to}
                      params={{ projectId: p.id }}
                      className="flex items-center gap-4 px-5 py-3 hover:bg-muted/40"
                    >
                      <div className="flex h-9 w-9 flex-none items-center justify-center rounded-md bg-accent/60 text-accent-foreground">
                        <FileText className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{p.title}</div>
                        <div className="truncate text-xs text-muted-foreground">{p.sourcePaper}</div>
                      </div>
                      <span className={`inline-flex items-center gap-1 text-xs ${meta.className}`}>
                        <Icon className={`h-3 w-3 ${p.status === "generating" ? "animate-spin" : ""}`} />
                        {meta.label}
                      </span>
                      <span className="w-16 text-right text-xs text-muted-foreground">
                        {formatDuration(p.durationMs)}
                      </span>
                      <span className="w-20 text-right text-xs text-muted-foreground">
                        {relTime(p.updatedAt)}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="flex flex-col gap-6">
          <div className="rounded-lg border border-border bg-card">
            <div className="border-b border-border px-5 py-3">
              <h2 className="text-sm font-semibold">Status breakdown</h2>
            </div>
            <ul className="p-4">
              {(Object.keys(STATUS_META) as ProjectStatus[]).map((s) => {
                const meta = STATUS_META[s];
                const Icon = meta.icon;
                const n = counts[s];
                const pct = projects.length ? Math.round((n / projects.length) * 100) : 0;
                return (
                  <li key={s} className="mb-3 last:mb-0">
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className={`inline-flex items-center gap-1.5 ${meta.className}`}>
                        <Icon className="h-3 w-3" />
                        {meta.label}
                      </span>
                      <span className="text-muted-foreground">{n}</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div className="h-full bg-primary/70" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="rounded-lg border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-3">
              <h2 className="text-sm font-semibold">Verifier flags</h2>
              <ShieldAlert className={`h-4 w-4 ${failFlags ? "text-destructive" : warnFlags ? "text-[color:var(--warning,#c47b1a)]" : "text-muted-foreground"}`} />
            </div>
            <div className="grid grid-cols-3 gap-2 p-4 text-center">
              <div>
                <div className="text-2xl font-semibold text-destructive">{failFlags}</div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Fail</div>
              </div>
              <div>
                <div className="text-2xl font-semibold">{warnFlags}</div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Warn</div>
              </div>
              <div>
                <div className="text-2xl font-semibold text-[color:var(--success)]">
                  {flags.length - failFlags - warnFlags}
                </div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Pass</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}