import type { CheckedStory } from "./explorer-story-types.js";
import type { StudioCoverage } from "./studio-model.js";

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  total?: number;
  count?: number;
  coverage?: StudioCoverage;
}

export async function api<T>(
  operation: string, args: Record<string, string | number | null | undefined> = {},
): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(args)) {
    if (value != null) query.set(key, String(value));
  }
  const response = await fetch("/api/v1/" + operation + "?" + query);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function draftStory(body: { prompt: string; element?: string; story?: string }): Promise<CheckedStory> {
  const reply = await fetch("/api/v1/story-chat", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!reply.ok) {
    const result: { error?: string } = await reply.json();
    throw new Error(result.error ?? "Story drafting failed.");
  }
  return reply.json();
}
