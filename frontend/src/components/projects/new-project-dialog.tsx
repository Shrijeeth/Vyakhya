import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UploadCloud, FileText, X } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { createProject } from "@/services/api";
import type { AspectRatio, AudienceLevel } from "@/services/types";

export function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [parseProgress, setParseProgress] = useState(0);
  const [audience, setAudience] = useState<AudienceLevel>("student");
  const [aspect, setAspect] = useState<AspectRatio>("16:9");
  const [language, setLanguage] = useState("en");
  const [targetLen, setTargetLen] = useState(5);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [userPrompt, setUserPrompt] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const reset = () => {
    setFile(null);
    setParseProgress(0);
    setAudience("student");
    setAspect("16:9");
    setLanguage("en");
    setTargetLen(5);
    setTtsEnabled(true);
    setUserPrompt("");
  };

  const simulateParse = (f: File) => {
    setFile(f);
    setParseProgress(0);
    let p = 0;
    const t = setInterval(() => {
      p = Math.min(100, p + 15 + Math.random() * 15);
      setParseProgress(p);
      if (p >= 100) clearInterval(t);
    }, 200);
  };

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Upload a PDF first.");
      return createProject({
        file,
        audience,
        aspectRatio: aspect,
        language,
        targetLengthMin: targetLen,
        ttsEnabled,
        userPrompt,
      });
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project created. Starting agent crew…");
      onOpenChange(false);
      reset();
      navigate({ to: "/projects/$projectId/pipeline", params: { projectId: p.id } });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>New video</DialogTitle>
          <DialogDescription>
            Upload a paper. The agent crew drafts an editable explainer video from it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {!file ? (
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files[0];
                if (f) simulateParse(f);
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
                dragOver
                  ? "border-primary bg-accent"
                  : "border-border hover:border-primary/60 hover:bg-muted/40"
              }`}
            >
              <UploadCloud className="h-8 w-8 text-muted-foreground" />
              <div className="text-sm font-medium">Drop PDF here or click to upload</div>
              <div className="text-xs text-muted-foreground">
                Single research paper, up to ~50 pages works best
              </div>
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) simulateParse(f);
                }}
              />
            </label>
          ) : (
            <div className="rounded-md border border-border bg-muted/30 p-3">
              <div className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-primary" />
                <span className="flex-1 truncate">{file.name}</span>
                <button
                  onClick={() => {
                    setFile(null);
                    setParseProgress(0);
                  }}
                  className="rounded p-1 text-muted-foreground hover:bg-muted"
                  aria-label="Remove file"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <Progress value={parseProgress} className="mt-2 h-1.5" />
              <div className="mt-1 text-[11px] text-muted-foreground">
                {parseProgress < 100 ? `Parsing… ${Math.round(parseProgress)}%` : "Parsed"}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-5">
            <div className="space-y-2">
              <Label>Audience level</Label>
              <RadioGroup
                value={audience}
                onValueChange={(v) => setAudience(v as AudienceLevel)}
                className="grid grid-cols-3 gap-2"
              >
                {(["layperson", "student", "expert"] as const).map((v) => (
                  <label
                    key={v}
                    className={`cursor-pointer rounded-md border px-2 py-2 text-center text-xs capitalize transition-colors ${
                      audience === v
                        ? "border-primary bg-accent text-accent-foreground"
                        : "border-border hover:bg-muted/50"
                    }`}
                  >
                    <RadioGroupItem value={v} className="sr-only" />
                    {v}
                  </label>
                ))}
              </RadioGroup>
            </div>
            <div className="space-y-2">
              <Label>Aspect ratio</Label>
              <RadioGroup
                value={aspect}
                onValueChange={(v) => setAspect(v as AspectRatio)}
                className="grid grid-cols-3 gap-2"
              >
                {(["16:9", "9:16", "1:1"] as const).map((v) => (
                  <label
                    key={v}
                    className={`cursor-pointer rounded-md border px-2 py-2 text-center text-xs transition-colors ${
                      aspect === v
                        ? "border-primary bg-accent text-accent-foreground"
                        : "border-border hover:bg-muted/50"
                    }`}
                  >
                    <RadioGroupItem value={v} className="sr-only" />
                    {v}
                  </label>
                ))}
              </RadioGroup>
            </div>

            <div className="space-y-2">
              <Label>Language</Label>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="es">Spanish</SelectItem>
                  <SelectItem value="fr">French</SelectItem>
                  <SelectItem value="de">German</SelectItem>
                  <SelectItem value="hi">Hindi</SelectItem>
                  <SelectItem value="ja">Japanese</SelectItem>
                  <SelectItem value="zh">Chinese</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Target length · {targetLen} min</Label>
              <Slider
                min={2}
                max={15}
                step={1}
                value={[targetLen]}
                onValueChange={(v) => setTargetLen(v[0])}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>
              Creative brief <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="Tone, focus, style… e.g. “Focus on the attention mechanism, playful tone, dark neon aesthetic, end with practical applications.”"
              className="min-h-[70px] text-sm"
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <div>
              <Label className="text-sm">Narration (TTS)</Label>
              <p className="text-[11px] text-muted-foreground">
                Generate a spoken voice-over. Turn off for a silent, text-only video.
              </p>
            </div>
            <Switch checked={ttsEnabled} onCheckedChange={setTtsEnabled} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!file || parseProgress < 100 || mutation.isPending}
          >
            {mutation.isPending ? "Starting…" : "Generate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
