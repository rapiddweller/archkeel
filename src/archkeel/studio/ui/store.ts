/** AD-290: the one store: the last API state, polled while the snapshot is not ready. */
import { useEffect, useState } from "preact/hooks";
import { readState, StudioState } from "./api";
import { ExploreState } from "./vocabulary";

export interface Snapshot {
  readonly state: StudioState | null;
  readonly error: string | null;
}

const RUNNING_MS = 1000;
const READY_MS = 5000;
let current: Snapshot = { state: null, error: null };
const listeners = new Set<() => void>();

async function poll(): Promise<void> {
  try {
    current = { state: await readState(), error: null };
  } catch (error) {
    current = { state: current.state, error: String(error) };
  }
  listeners.forEach((listener) => listener());
  const waiting = current.state?.explore !== ExploreState.DONE;
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
