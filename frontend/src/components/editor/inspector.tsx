import { useEditorStore } from "@/store/editor-store";
import type { Scene, VisualType } from "@/services/types";
import { visualTypeSchemas, type ParamField } from "@/services/api";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { BookOpen, ExternalLink } from "lucide-react";

export function Inspector() {
  const scene = useEditorStore((s) => s.project?.scenes.find((sc) => sc.id === s.selectedSceneId) ?? null);
  const update = useEditorStore((s) => s.updateScene);

  if (!scene) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        Select a scene to edit it.
      </div>
    );
  }

  const patch = (p: Partial<Scene>) => update(scene.id, p);
  const schema = visualTypeSchemas[scene.visualType];

  return (
    <ScrollArea className="h-full">
      <div className="space-y-6 p-5">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Scene {scene.index}
          </div>
          <div className="mt-0.5 text-sm font-semibold">Inspector</div>
        </div>

        <section className="space-y-2">
          <Label>Narration</Label>
          <Textarea
            value={scene.narration}
            onChange={(e) => patch({ narration: e.target.value })}
            className="min-h-[120px] resize-y font-[500] leading-relaxed"
          />
          <p className="text-[11px] text-muted-foreground">
            Rich text lives here in the full build — for now the narration is edited as plain text.
          </p>
        </section>

        <section className="space-y-2">
          <Label>Visual type</Label>
          <Select value={scene.visualType} onValueChange={(v) => patch({ visualType: v as VisualType, params: {} })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(visualTypeSchemas).map(([k, s]) => (
                <SelectItem key={k} value={k}>{s.label} <span className="text-muted-foreground">· {k}</span></SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-[11px] text-muted-foreground">{schema.description}</p>
        </section>

        <section className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Parameters
          </div>
          {schema.fields.map((f) => (
            <ParamInput
              key={f.key}
              field={f}
              value={scene.params[f.key]}
              onChange={(v) => patch({ params: { ...scene.params, [f.key]: v } })}
            />
          ))}
        </section>

        <section className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label>Caption style</Label>
            <Select value={scene.captionStyle} onValueChange={(v) => patch({ captionStyle: v as Scene["captionStyle"] })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                <SelectItem value="minimal">Minimal</SelectItem>
                <SelectItem value="bold">Bold</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Transition</Label>
            <Select value={scene.transition} onValueChange={(v) => patch({ transition: v as Scene["transition"] })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cut">Cut</SelectItem>
                <SelectItem value="fade">Fade</SelectItem>
                <SelectItem value="slide">Slide</SelectItem>
                <SelectItem value="wipe">Wipe</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </section>

        <section className="space-y-2">
          <Label>Duration</Label>
          <div className="flex items-center gap-2">
            <Select
              value={scene.durationMs === "auto" ? "auto" : "manual"}
              onValueChange={(v) => patch({ durationMs: v === "auto" ? "auto" : 6000 })}
            >
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto</SelectItem>
                <SelectItem value="manual">Manual</SelectItem>
              </SelectContent>
            </Select>
            {scene.durationMs !== "auto" && (
              <Input
                type="number"
                min={500}
                step={100}
                value={scene.durationMs}
                onChange={(e) => patch({ durationMs: Number(e.target.value) })}
                className="w-28"
              />
            )}
            <span className="text-xs text-muted-foreground">ms</span>
          </div>
        </section>

        <section className="space-y-2">
          <Label className="flex items-center gap-1.5"><BookOpen className="h-3.5 w-3.5" />Source citations</Label>
          {scene.citations.length === 0 ? (
            <div className="rounded-md border border-dashed border-border p-3 text-[11px] text-muted-foreground">
              No citations linked yet.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {scene.citations.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs">
                  <span><span className="font-medium">{c.label}</span> <span className="text-muted-foreground">{c.sourceSpan}</span></span>
                  <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]">
                    View source <ExternalLink className="ml-1 h-3 w-3" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </ScrollArea>
  );
}

function ParamInput({ field, value, onChange }: { field: ParamField; value: unknown; onChange: (v: unknown) => void }) {
  if (field.kind === "text") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}</Label>
        <Input value={String(value ?? "")} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />
      </div>
    );
  }
  if (field.kind === "textarea") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}</Label>
        <Textarea value={String(value ?? "")} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs" />
      </div>
    );
  }
  if (field.kind === "number") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}</Label>
        <Input type="number" value={Number(value ?? 0)} onChange={(e) => onChange(Number(e.target.value))} />
      </div>
    );
  }
  if (field.kind === "list") {
    const arr = Array.isArray(value) ? (value as string[]) : [];
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}</Label>
        <Textarea
          value={arr.join("\n")}
          onChange={(e) => onChange(e.target.value.split("\n").filter(Boolean))}
          className="min-h-[80px] font-mono text-xs"
        />
      </div>
    );
  }
  if (field.kind === "bars") {
    const arr = Array.isArray(value) ? (value as { label: string; value: number }[]) : [];
    const text = arr.map((r) => `${r.label},${r.value}`).join("\n");
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}</Label>
        <Textarea
          value={text}
          onChange={(e) => {
            const rows = e.target.value
              .split("\n")
              .map((l) => l.split(","))
              .filter((r) => r.length === 2)
              .map(([label, v]) => ({ label: label.trim(), value: Number(v) }));
            onChange(rows);
          }}
          className="min-h-[80px] font-mono text-xs"
          placeholder={"RNN,25.2\nTransformer,28.4"}
        />
      </div>
    );
  }
  return null;
}