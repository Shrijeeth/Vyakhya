import { useEffect, useRef } from "react";
import { Play, Pause, SkipBack, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";

// Live HTML preview. The real HyperFrames renderer drops in by replacing
// the iframe srcDoc source — the { html, seekMs, totalMs } contract stays.
export interface PreviewPlayerProps {
  html: string;
  seekMs: number;
  totalMs: number;
  playing: boolean;
  onSeek: (ms: number) => void;
  onPlayPause: () => void;
  onStep: (deltaMs: number) => void;
  aspectRatio: "16:9" | "9:16" | "1:1";
}

function fmt(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function PreviewPlayer({
  html,
  seekMs,
  totalMs,
  playing,
  onSeek,
  onPlayPause,
  onStep,
  aspectRatio,
}: PreviewPlayerProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    if (iframeRef.current) iframeRef.current.srcdoc = html;
  }, [html]);

  // Drive the seekable runtime inside the iframe: post the current time on every
  // scrub/tick. The composition is a pure function of t (active scene + frozen
  // entrance animations), so playback is just a stream of seeks from the parent.
  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage({ type: "hf-seek", t: Math.round(seekMs) }, "*");
  }, [seekMs, html]);

  const aspectClass =
    aspectRatio === "9:16"
      ? "aspect-[9/16] max-h-full"
      : aspectRatio === "1:1"
        ? "aspect-square max-h-full"
        : "aspect-video";

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 items-center justify-center overflow-hidden bg-muted/30 p-6">
        <div
          className={`${aspectClass} w-full max-w-[1100px] overflow-hidden rounded-lg border border-border bg-card shadow-lg`}
        >
          <iframe
            ref={iframeRef}
            title="Live preview"
            sandbox="allow-scripts"
            className="h-full w-full"
            onLoad={() =>
              iframeRef.current?.contentWindow?.postMessage(
                { type: "hf-seek", t: Math.round(seekMs) },
                "*",
              )
            }
          />
        </div>
      </div>
      <div className="border-t border-border bg-card px-6 py-3">
        <div className="mb-2 flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2 py-0.5 text-accent-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            Live preview (HTML)
          </span>
          <span className="tabular-nums">
            {fmt(seekMs)} / {fmt(totalMs)}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Button size="icon" variant="ghost" onClick={() => onStep(-1000)} aria-label="Step back">
            <SkipBack className="h-4 w-4" />
          </Button>
          <Button size="icon" onClick={onPlayPause} aria-label={playing ? "Pause" : "Play"}>
            {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => onStep(1000)}
            aria-label="Step forward"
          >
            <SkipForward className="h-4 w-4" />
          </Button>
          <Slider
            className="flex-1"
            min={0}
            max={Math.max(totalMs, 1)}
            step={100}
            value={[Math.min(seekMs, totalMs)]}
            onValueChange={(v) => onSeek(v[0])}
          />
        </div>
      </div>
    </div>
  );
}
