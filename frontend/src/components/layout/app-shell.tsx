import { Link, useRouterState } from "@tanstack/react-router";
import {
  BookOpen,
  FileText,
  FolderKanban,
  MessageSquareCode,
  Settings2,
  ExternalLink,
  CheckCircle2,
  LayoutDashboard,
} from "lucide-react";
import type { ReactNode } from "react";
import { Wordmark } from "./wordmark";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/sonner";

const NAV: { to: string; label: string; icon: typeof FolderKanban; exact?: boolean }[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/", label: "Projects", icon: FolderKanban, exact: true },
  { to: "/model-config", label: "Model Config", icon: Settings2 },
  { to: "/agent-prompts", label: "Agent Prompts", icon: MessageSquareCode },
  { to: "/settings", label: "Settings", icon: FileText },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  const projectMatch = pathname.match(/^\/projects\/([^/]+)\/([^/]+)/);
  const projectId = projectMatch?.[1];
  const stage = projectMatch?.[2];
  const projectName = projectId ? `Project ${projectId} · ${stage}` : undefined;
  return (
    // h-screen (not min-h-screen): full-height pages like the editor need a
    // bounded height chain — with min-h the columns grow with content and
    // internal panes (scene list, preview) can never scroll. `main` scrolls.
    <div className="h-screen overflow-hidden bg-background text-foreground">
      <div className="grid h-screen grid-cols-[240px_1fr] grid-rows-[minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col overflow-y-auto border-r border-border bg-sidebar text-sidebar-foreground">
          <div className="flex h-14 items-center border-b border-sidebar-border px-4">
            <Wordmark />
          </div>
          <nav className="flex flex-col gap-0.5 p-2">
            {NAV.map((item) => {
              const active = item.exact ? pathname === item.to : pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
            <a
              href="https://github.com/"
              target="_blank"
              rel="noreferrer"
              className="mt-1 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
            >
              <BookOpen className="h-4 w-4" />
              Docs
              <ExternalLink className="ml-auto h-3 w-3 opacity-60" />
            </a>
          </nav>
          <div className="mt-auto p-4 text-[11px] leading-relaxed text-sidebar-foreground/60">
            Self-hosted · single workspace
          </div>
        </aside>

        <div className="flex min-h-0 flex-col">
          <header className="flex h-14 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
            <div className="flex items-center gap-3">
              {projectName ? (
                <>
                  <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
                    Projects
                  </Link>
                  <span className="text-muted-foreground">/</span>
                  <span className="text-sm font-medium">{projectName}</span>
                </>
              ) : (
                <span className="text-sm text-muted-foreground">
                  Turn documents into editable explainer videos.
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground">
                <CheckCircle2 className="h-3 w-3 text-[color:var(--success)]" />
                Keys configured
              </span>
              <ThemeToggle />
            </div>
          </header>
          <main className="min-h-0 flex-1 overflow-auto">{children}</main>
        </div>
      </div>
      <Toaster position="top-right" richColors closeButton />
    </div>
  );
}
