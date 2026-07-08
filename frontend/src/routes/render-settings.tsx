import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { getRenderSettings, saveRenderSettings } from "@/services/api";
import type { RenderSettings } from "@/services/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";

export const Route = createFileRoute("/render-settings")({
  component: RenderSettingsPage,
});

const PRESETS = [
  { label: "1080p 16:9", width: 1920, height: 1080 },
  { label: "720p 16:9", width: 1280, height: 720 },
  { label: "1080×1920 9:16", width: 1080, height: 1920 },
  { label: "1080×1080 1:1", width: 1080, height: 1080 },
];

function RenderSettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["render-settings"], queryFn: getRenderSettings });
  const [local, setLocal] = useState<RenderSettings | null>(null);
  const settings = local ?? data ?? null;
  const setField = <K extends keyof RenderSettings>(k: K, v: RenderSettings[K]) => {
    if (!settings) return;
    setLocal({ ...settings, [k]: v });
  };

  const saveMut = useMutation({
    mutationFn: (s: RenderSettings) => saveRenderSettings(s),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["render-settings"] });
      toast.success("Settings saved");
    },
  });

  if (!settings) return null;

  const presetMatch = PRESETS.find(
    (p) => p.width === settings.width && p.height === settings.height,
  );

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <div className="mb-1 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Render settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Global export defaults — start renders from a project's editor (Export).
          </p>
        </div>
        <Button onClick={() => saveMut.mutate(settings)} disabled={saveMut.isPending}>
          <Save className="mr-1.5 h-4 w-4" />
          Save defaults
        </Button>
      </div>

      <div className="mt-8 space-y-6">
        <section className="rounded-lg border border-border bg-card p-5">
          <div className="mb-4 text-sm font-semibold">Output</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label>Resolution preset</Label>
              <Select
                value={presetMatch?.label ?? "custom"}
                onValueChange={(v) => {
                  if (v === "custom") return;
                  const p = PRESETS.find((x) => x.label === v);
                  if (p) {
                    setField("width", p.width);
                    setField("height", p.height);
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRESETS.map((p) => (
                    <SelectItem key={p.label} value={p.label}>
                      {p.label}
                    </SelectItem>
                  ))}
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label>Width</Label>
                <Input
                  type="number"
                  value={settings.width}
                  onChange={(e) => setField("width", Number(e.target.value))}
                />
              </div>
              <div className="space-y-1">
                <Label>Height</Label>
                <Input
                  type="number"
                  value={settings.height}
                  onChange={(e) => setField("height", Number(e.target.value))}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Frame rate</Label>
              <Select
                value={String(settings.fps)}
                onValueChange={(v) => setField("fps", Number(v) as RenderSettings["fps"])}
              >
                <SelectTrigger>
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
              <Label>Format</Label>
              <Select
                value={settings.format}
                onValueChange={(v) => setField("format", v as RenderSettings["format"])}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mp4">MP4</SelectItem>
                  <SelectItem value="webm">WebM</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Quality · {settings.quality}</Label>
              <Slider
                min={30}
                max={100}
                step={1}
                value={[settings.quality]}
                onValueChange={(v) => setField("quality", v[0])}
              />
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-border bg-card p-5">
          <div className="mb-4 text-sm font-semibold">Audio mix</div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label>Master · {settings.audioMasterDb} dB</Label>
              <Slider
                min={-24}
                max={6}
                step={1}
                value={[settings.audioMasterDb]}
                onValueChange={(v) => setField("audioMasterDb", v[0])}
              />
            </div>
            <div className="space-y-1">
              <Label>Narration · {settings.audioNarrationDb} dB</Label>
              <Slider
                min={-24}
                max={6}
                step={1}
                value={[settings.audioNarrationDb]}
                onValueChange={(v) => setField("audioNarrationDb", v[0])}
              />
            </div>
            <div className="space-y-1">
              <Label>Music · {settings.audioMusicDb} dB</Label>
              <Slider
                min={-40}
                max={0}
                step={1}
                value={[settings.audioMusicDb]}
                onValueChange={(v) => setField("audioMusicDb", v[0])}
              />
            </div>
          </div>
        </section>

        <Collapsible>
          <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border border-border bg-card px-5 py-3 text-sm font-semibold hover:bg-muted/40">
            Advanced
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          </CollapsibleTrigger>
          <CollapsibleContent className="rounded-b-lg border-x border-b border-border bg-card p-5">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Codec</Label>
                <Select
                  value={settings.codec}
                  onValueChange={(v) => setField("codec", v as RenderSettings["codec"])}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="h264">H.264</SelectItem>
                    <SelectItem value="h265">H.265 / HEVC</SelectItem>
                    <SelectItem value="vp9">VP9</SelectItem>
                    <SelectItem value="av1">AV1</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Worker concurrency · {settings.workers}</Label>
                <Slider
                  min={1}
                  max={16}
                  step={1}
                  value={[settings.workers]}
                  onValueChange={(v) => setField("workers", v[0])}
                />
              </div>
              <div className="col-span-2 flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2.5">
                <div>
                  <Label className="text-sm">GPU acceleration</Label>
                  <p className="text-[11px] text-muted-foreground">
                    Use hardware encoders when available.
                  </p>
                </div>
                <Switch checked={settings.gpu} onCheckedChange={(v) => setField("gpu", v)} />
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>

      </div>
    </div>
  );
}
