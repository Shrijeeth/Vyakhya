import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Play, AlertTriangle, ExternalLink } from "lucide-react";
import {
  getRenderSettings,
  listRenders,
  startRender,
  subscribeRenderJob,
} from "@/services/api";
import type { RenderJob, RenderSettings } from "@/services/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Project-scoped export: start a background render job and watch its progress.
// The job runs server-side — closing this dialog (or the tab) doesn't stop it;
// reopening re-attaches to the running job via its persisted state.
export function RenderDialog({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [job, setJob] = useState<RenderJob | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);

  const { data: defaults } = useQuery({
    queryKey: ["render-settings"],
    queryFn: getRenderSettings,
    enabled: open,
  });
  const { data: history } = useQuery({
    queryKey: ["renders", projectId],
    queryFn: () => listRenders(projectId),
    enabled: open,
  });

  const [overrides, setOverrides] = useState<Partial<RenderSettings>>({});
  const settings = defaults ? { ...defaults, ...overrides } : null;

  const attach = (jobId: string) => {
    unsubRef.current?.();
    unsubRef.current = subscribeRenderJob(jobId, (j) => {
      setJob(j);
      if (j.status === "done" || j.status === "error") {
        qc.invalidateQueries({ queryKey: ["renders", projectId] });
      }
    });
  };

  // Re-attach to an in-flight job when the dialog opens (e.g. after a reload).
  useEffect(() => {
    if (!open || job || !history) return;
    const running = history.find((j) => j.status === "running" || j.status === "queued");
    if (running) {
      setJob(running);
      attach(running.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, history]);

  // Detach the SSE reader on unmount (the job itself keeps running server-side).
  useEffect(() => () => unsubRef.current?.(), []);

  const start = async () => {
    if (!settings) return;
    const j = await startRender(projectId, settings);
    setJob(j);
    attach(j.id);
    qc.invalidateQueries({ queryKey: ["renders", projectId] });
  };

  const active = job && (job.status === "running" || job.status === "queued");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Download className="mr-1.5 h-3.5 w-3.5" />
          Export
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Export video</DialogTitle>
          <DialogDescription>
            Renders in the background with HyperFrames — you can close this dialog and come back.
          </DialogDescription>
        </DialogHeader>

        {settings && (
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Frame rate</Label>
              <Select
                value={String(settings.fps)}
                onValueChange={(v) =>
                  setOverrides((o) => ({ ...o, fps: Number(v) as RenderSettings["fps"] }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="24">24 fps</SelectItem>
                  <SelectItem value="30">30 fps</SelectItem>
                  <SelectItem value="60">60 fps</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Quality</Label>
              <Select
                value={settings.quality >= 80 ? "high" : settings.quality >= 40 ? "standard" : "draft"}
                onValueChange={(v) =>
                  setOverrides((o) => ({
                    ...o,
                    quality: v === "high" ? 90 : v === "standard" ? 60 : 30,
                  }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Format</Label>
              <Select
                value={settings.format}
                onValueChange={(v) =>
                  setOverrides((o) => ({ ...o, format: v as RenderSettings["format"] }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mp4">MP4</SelectItem>
                  <SelectItem value="webm">WebM</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="col-span-3 text-[11px] text-muted-foreground">
              Resolution, codec, and audio mix come from{" "}
              <a href="/render-settings" className="underline">
                Render Settings
              </a>
              .
            </p>
          </div>
        )}

        <Button onClick={start} disabled={!settings || !!active} className="w-full">
          {active ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-1.5 h-4 w-4" />
          )}
          {active ? "Rendering…" : "Start render"}
        </Button>

        {job && (
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <div className="flex items-center gap-3">
              {job.status === "error" ? (
                <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
              ) : job.status === "done" ? (
                <Download className="h-4 w-4 shrink-0 text-primary" />
              ) : (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
              )}
              <Progress value={job.progress * 100} className="h-1.5 flex-1" />
              <span className="text-xs tabular-nums text-muted-foreground">
                {Math.round(job.progress * 100)}%
              </span>
            </div>
            {job.status === "error" && (
              <p className="mt-2 break-words text-[11px] text-destructive">
                {job.error ?? "Render failed"}
              </p>
            )}
            {job.status === "done" && job.outputUrl && (
              <div className="mt-2 flex justify-end">
                <Button size="sm" asChild>
                  <a href={job.outputUrl} target="_blank" rel="noreferrer">
                    <Download className="mr-1.5 h-3.5 w-3.5" />
                    Download
                  </a>
                </Button>
              </div>
            )}
          </div>
        )}

        {history && history.length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Previous renders
            </div>
            <div className="max-h-40 space-y-1 overflow-auto">
              {history.map((h) => (
                <div
                  key={h.id}
                  className="flex items-center justify-between rounded border border-border px-2.5 py-1.5 text-xs"
                >
                  <span className="capitalize">
                    {h.status}
                    {h.createdAt ? ` · ${new Date(h.createdAt).toLocaleString()}` : ""}
                  </span>
                  {h.outputUrl ? (
                    <a
                      href={h.outputUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      Open <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : (
                    <span className="text-muted-foreground">
                      {h.status === "error" ? "failed" : `${Math.round(h.progress * 100)}%`}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
