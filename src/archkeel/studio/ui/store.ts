/** AD-290: the one store: the last API state, polled until a valid snapshot and its model are ready. */
import { useEffect, useState } from "preact/hooks";
import { StudioState, readGraph, readState } from "./api";
import { Model, buildModel } from "./model";
import { ExploreState } from "./vocabulary";

interface Snapshot {
  readonly state: StudioState | null;
  readonly error: string | null;
  /** The indexed call graph; null until the explore run writes a valid snapshot. */
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
    if (
      (state.explore === ExploreState.DONE || state.explore === ExploreState.INCOMPLETE) &&
      current.model === null
    ) {
      const graph = await readGraph();
      current = { ...current, model: graph === null ? null : buildModel(graph) };
    }
  } catch (error) {
    current = { ...current, error: String(error) };
  }
  listeners.forEach((listener) => listener());
  // A failed read is not asked again each second: the snapshot does not mend itself.
  const running = current.state?.explore === ExploreState.IDLE || current.state?.explore === ExploreState.RUNNING;
  const loading =
    (current.state?.explore === ExploreState.DONE || current.state?.explore === ExploreState.INCOMPLETE) &&
    current.model === null;
  const waiting = (running || loading) && current.error === null;
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
