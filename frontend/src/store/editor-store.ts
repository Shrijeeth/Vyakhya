import { create } from "zustand";
import type { EditorProject, Scene } from "@/services/types";

interface EditorState {
  project: EditorProject | null;
  selectedSceneId: string | null;
  dirtySceneIds: Set<string>;
  currentTimeMs: number;
  playing: boolean;

  setProject: (p: EditorProject) => void;
  selectScene: (id: string) => void;
  updateScene: (id: string, patch: Partial<Scene>) => void;
  reorderScenes: (fromIndex: number, toIndex: number) => void;
  addScene: () => void;
  duplicateScene: (id: string) => void;
  deleteScene: (id: string) => void;
  markClean: (id: string) => void;
  setCurrentTime: (ms: number) => void;
  setPlaying: (playing: boolean) => void;
}

const newSceneAt = (index: number): Scene => ({
  id: `s${Date.now()}`,
  index,
  narration: "New scene narration…",
  visualType: "title.card",
  params: { title: "New scene", subtitle: "" },
  captionStyle: "minimal",
  transition: "fade",
  durationMs: 6000,
  citations: [],
});

const reindex = (scenes: Scene[]): Scene[] => scenes.map((s, i) => ({ ...s, index: i + 1 }));

export const useEditorStore = create<EditorState>((set) => ({
  project: null,
  selectedSceneId: null,
  dirtySceneIds: new Set<string>(),
  currentTimeMs: 0,
  playing: false,

  setProject: (project) =>
    set({
      project,
      selectedSceneId: project.scenes[0]?.id ?? null,
      dirtySceneIds: new Set<string>(),
      currentTimeMs: 0,
      playing: false,
    }),

  selectScene: (id) => set({ selectedSceneId: id }),

  updateScene: (id, patch) =>
    set((s) => {
      if (!s.project) return s;
      const scenes = s.project.scenes.map((sc) => (sc.id === id ? { ...sc, ...patch } : sc));
      const dirty = new Set(s.dirtySceneIds);
      dirty.add(id);
      return { project: { ...s.project, scenes }, dirtySceneIds: dirty };
    }),

  reorderScenes: (fromIndex, toIndex) =>
    set((s) => {
      if (!s.project) return s;
      const scenes = [...s.project.scenes];
      const [moved] = scenes.splice(fromIndex, 1);
      scenes.splice(toIndex, 0, moved);
      return { project: { ...s.project, scenes: reindex(scenes) } };
    }),

  addScene: () =>
    set((s) => {
      if (!s.project) return s;
      const scene = newSceneAt(s.project.scenes.length + 1);
      return {
        project: { ...s.project, scenes: [...s.project.scenes, scene] },
        selectedSceneId: scene.id,
      };
    }),

  duplicateScene: (id) =>
    set((s) => {
      if (!s.project) return s;
      const idx = s.project.scenes.findIndex((sc) => sc.id === id);
      if (idx < 0) return s;
      const copy: Scene = { ...s.project.scenes[idx], id: `s${Date.now()}` };
      const scenes = [...s.project.scenes];
      scenes.splice(idx + 1, 0, copy);
      return {
        project: { ...s.project, scenes: reindex(scenes) },
        selectedSceneId: copy.id,
      };
    }),

  deleteScene: (id) =>
    set((s) => {
      if (!s.project) return s;
      const scenes = reindex(s.project.scenes.filter((sc) => sc.id !== id));
      return {
        project: { ...s.project, scenes },
        selectedSceneId: scenes[0]?.id ?? null,
      };
    }),

  markClean: (id) =>
    set((s) => {
      const dirty = new Set(s.dirtySceneIds);
      dirty.delete(id);
      return { dirtySceneIds: dirty };
    }),

  setCurrentTime: (currentTimeMs) => set({ currentTimeMs }),
  setPlaying: (playing) => set({ playing }),
}));
