export const system = { id: "system", name: "System", kind: "system" };
export const state = {
    ancestors: [system], items: [], cursor: null, selected: null, edges: [], request: 0,
    hops: [], storyIndex: -1, zoom: 1, search: null,
};
export const pageTrails = new Map();
export const known = new Map([[system.id, system]]);
