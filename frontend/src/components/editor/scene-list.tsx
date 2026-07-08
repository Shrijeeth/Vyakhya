import {
  GripVertical,
  Plus,
  Copy,
  Trash2,
  Type,
  ListChecks,
  Image as ImageIcon,
  Sigma,
  BarChart3,
  Network,
  Columns2,
  Zap,
  Rotate3d,
  Code2,
} from "lucide-react";
import type { Scene, VisualType } from "@/services/types";
import { useEditorStore } from "@/store/editor-store";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

const VISUAL_ICON: Record<VisualType, React.ComponentType<{ className?: string }>> = {
  "title.card": Type,
  "bullet.reveal": ListChecks,
  "figure.callout": ImageIcon,
  "equation.build": Sigma,
  "dataviz.bar": BarChart3,
  "diagram.attention": Network,
  "comparison.split": Columns2,
  "kinetic.type": Zap,
  "orbit.3d": Rotate3d,
  "custom.html": Code2,
};

function fmtDuration(d: Scene["durationMs"]) {
  if (d === "auto") return "auto";
  const s = Math.round(d / 100) / 10;
  return `${s}s`;
}

export function SceneList() {
  const scenes = useEditorStore((s) => s.project?.scenes ?? []);
  const selectedId = useEditorStore((s) => s.selectedSceneId);
  const dirtyIds = useEditorStore((s) => s.dirtySceneIds);
  const selectScene = useEditorStore((s) => s.selectScene);
  const reorder = useEditorStore((s) => s.reorderScenes);
  const addScene = useEditorStore((s) => s.addScene);
  const duplicateScene = useEditorStore((s) => s.duplicateScene);
  const deleteScene = useEditorStore((s) => s.deleteScene);

  const totalMs = scenes.reduce((a, s) => a + (s.durationMs === "auto" ? 6000 : s.durationMs), 0);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-sm font-semibold">Scenes</div>
          <div className="text-[11px] text-muted-foreground">
            {scenes.length} scenes · {(totalMs / 1000).toFixed(0)}s total
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={addScene}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <ol className="space-y-1.5 p-2">
          {scenes.map((s, idx) => {
            const Icon = VISUAL_ICON[s.visualType];
            const isSelected = s.id === selectedId;
            const isDirty = dirtyIds.has(s.id);
            return (
              <li
                key={s.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData("text/plain", String(idx))}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const from = Number(e.dataTransfer.getData("text/plain"));
                  if (!Number.isNaN(from) && from !== idx) reorder(from, idx);
                }}
                onClick={() => selectScene(s.id)}
                className={`group flex cursor-pointer items-start gap-2 rounded-md border p-2.5 transition-colors ${
                  isSelected
                    ? "border-primary bg-accent"
                    : "border-border bg-card hover:bg-muted/50"
                }`}
              >
                <GripVertical className="mt-0.5 h-3.5 w-3.5 cursor-grab text-muted-foreground opacity-0 group-hover:opacity-100" />
                <span className="mt-0.5 w-5 text-center text-[11px] font-medium tabular-nums text-muted-foreground">
                  {s.index}
                </span>
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-xs leading-snug">{s.narration}</div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span>{s.visualType}</span>
                    <span>·</span>
                    <span>{fmtDuration(s.durationMs)}</span>
                    {isDirty && (
                      <span className="rounded-full bg-[color:var(--warning)]/20 px-1.5 text-[color:var(--warning)]">
                        unsaved
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      duplicateScene(s.id);
                    }}
                    className="rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                    aria-label="Duplicate"
                  >
                    <Copy className="h-3 w-3" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteScene(s.id);
                    }}
                    className="rounded p-1 text-muted-foreground hover:bg-background hover:text-destructive"
                    aria-label="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      </ScrollArea>

      <TimelineStrip />
    </div>
  );
}

function TimelineStrip() {
  const scenes = useEditorStore((s) => s.project?.scenes ?? []);
  const selectedId = useEditorStore((s) => s.selectedSceneId);
  const selectScene = useEditorStore((s) => s.selectScene);
  const setCurrentTime = useEditorStore((s) => s.setCurrentTime);
  const totalMs = scenes.reduce((a, s) => a + (s.durationMs === "auto" ? 6000 : s.durationMs), 0);

  return (
    <div className="border-t border-border bg-muted/30 p-3">
      <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        Timeline
      </div>
      <div className="flex h-8 gap-0.5 overflow-hidden rounded-md">
        {scenes.map((s) => {
          const dur = s.durationMs === "auto" ? 6000 : s.durationMs;
          const pct = totalMs ? (dur / totalMs) * 100 : 0;
          const isSelected = s.id === selectedId;
          let start = 0;
          for (const p of scenes) {
            if (p.id === s.id) break;
            start += p.durationMs === "auto" ? 6000 : p.durationMs;
          }
          return (
            <button
              key={s.id}
              onClick={() => {
                selectScene(s.id);
                setCurrentTime(start);
              }}
              style={{ width: `${pct}%` }}
              className={`flex items-center justify-center overflow-hidden text-[10px] font-medium transition-colors ${
                isSelected
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground hover:bg-primary/20"
              }`}
              title={`Scene ${s.index}`}
            >
              {s.index}
            </button>
          );
        })}
      </div>
    </div>
  );
}
