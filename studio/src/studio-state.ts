import type { StudioItem, StudioEdge } from "./studio-model.js";
import type { StoryHop } from "./explorer-story-types.js";

export const system: StudioItem = { id: "system", name: "System", kind: "system" };
interface State {
  ancestors: StudioItem[];
  items: StudioItem[];
  cursor: string | null;
  selected: string | null;
  edges: StudioEdge[];
  request: number;
  view: number;
  hops: StoryHop[];
  storyIndex: number;
  zoom: number;
  search: string | null;
}
export const state: State = {
  ancestors: [system], items: [], cursor: null, selected: null, edges: [], request: 0, view: 0,
  hops: [], storyIndex: -1, zoom: 1, search: null,
};
export const pageTrails = new Map<string, string[]>();
export const known = new Map([[system.id, system]]);
