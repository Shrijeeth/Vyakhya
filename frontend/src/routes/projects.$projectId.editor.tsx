import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { compileScenePreview, getEditorProject } from "@/services/api";
import { useEditorStore } from "@/store/editor-store";
import { Button } from "@/components/ui/button";
import { SceneList } from "@/components/editor/scene-list";
import { Inspector } from "@/components/editor/inspector";
import { PreviewPlayer } from "@/components/editor/preview-player";

export const Route = createFileRoute("/projects/$projectId/editor")({
  component: EditorPage,
});

function EditorPage() {
  const { projectId } = Route.useParams();
  const navigate = useNavigate();
  const setProject = useEditorStore((s) => s.setProject);
  const project = useEditorStore((s) => s.project);
  const scene = useEditorStore(
    (s) => s.project?.scenes.find((sc) => sc.id === s.selectedSceneId) ?? null,
  );
  const currentTime = useEditorStore((s) => s.currentTimeMs);
  const playing = useEditorStore((s) => s.playing);
  const setCurrentTime = useEditorStore((s) => s.setCurrentTime);
  const setPlaying = useEditorStore((s) => s.setPlaying);

  const { data } = useQuery({
    queryKey: ["editor-project", projectId],
    queryFn: () => getEditorProject(projectId),
  });

  // Re-seed the store whenever the server data changes — not only when the
  // project id differs. The pipeline persists scenes after the editor first
  // loads (0 scenes), so a later refetch must be able to fill them in; an
  // id-only guard would leave the editor stuck showing the empty first load.
  useEffect(() => {
    if (data) setProject(data);
  }, [data, setProject]);

  const [previewHtml, setPreviewHtml] = useState<string>("");
  useEffect(() => {
    if (!scene) return;
    let cancelled = false;
    compileScenePreview(scene).then((html) => {
      if (!cancelled) setPreviewHtml(html);
    });
    return () => {
      cancelled = true;
    };
  }, [scene]);

  // fake playback tick
  useEffect(() => {
    if (!playing || !project) return;
    const t = setInterval(() => {
      setCurrentTime(Math.min(currentTime + 100, project.totalDurationMs));
    }, 100);
    return () => clearInterval(t);
  }, [playing, currentTime, project, setCurrentTime]);

  if (!project) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading editor…
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border bg-card/40 px-6 py-3">
        <div>
          <h1 className="text-sm font-semibold">{project.title}</h1>
          <p className="text-[11px] text-muted-foreground">
            Editable explainer · {project.scenes.length} scenes · {project.aspectRatio}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate({ to: "/projects/$projectId/pipeline", params: { projectId } })}
          >
            View pipeline
          </Button>
          <Button size="sm" onClick={() => navigate({ to: "/render-settings" })}>
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Export
          </Button>
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[300px_1fr_360px]">
        <div className="min-h-0 border-r border-border bg-card/30">
          <SceneList />
        </div>
        <div className="min-h-0 border-r border-border">
          <PreviewPlayer
            html={previewHtml}
            seekMs={currentTime}
            totalMs={project.totalDurationMs}
            playing={playing}
            onSeek={setCurrentTime}
            onPlayPause={() => setPlaying(!playing)}
            onStep={(d) =>
              setCurrentTime(Math.max(0, Math.min(project.totalDurationMs, currentTime + d)))
            }
            aspectRatio={project.aspectRatio}
          />
        </div>
        <div className="min-h-0 bg-card/20">
          <Inspector />
        </div>
      </div>
    </div>
  );
}
