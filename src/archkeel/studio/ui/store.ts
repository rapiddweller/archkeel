/** AD-290: the one store: the last API state, polled while the snapshot is not ready, and its model. */
import { useEffect, useState } from "preact/hooks";
import { StudioState, readGraph, readState } from "./api";
import { Model, buildModel } from "./model";
import { ExploreState } from "./vocabulary";

export interface Snapshot {
  readonly state: StudioState | null;
  readonly error: string | null;
  /** The indexed call graph; null until the explore run is done. */
  readonly model: Model | null;
}

const RUNNING_MS = 1000;
const READY_MS = 5000;
let current: Snapshot = { state: null, error: null, model: null };
const listeners = new Set<() => void>();

async function poll(): Promise<void> {
  try {
    const state = await readState();
    current = { ...current, state, error: null };
    if (state.explore === ExploreState.DONE && current.model === null) {
      const graph = await readGraph();
      current = { ...current, model: graph === null ? null : buildModel(graph) };
    }
  } catch (error) {
    current = { ...current, error: String(error) };
  }
  listeners.forEach((listener) => listener());
  // A failed read is not asked again each second: the snapshot does not mend itself.
  const waiting = (current.state?.explore !== ExploreState.DONE || current.model === null) && current.error === null;
  setTimeout(poll, waiting ? RUNNING_MS : READY_MS);
}

export function startStore(): void {
  void poll();
}

export function useStudio(): Snapshot {
  const [snapshot, setSnapshot] = useState(current);
  useEffect(() => {
    const listener = (): void => setSnapshot(current);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return snapshot;
}
