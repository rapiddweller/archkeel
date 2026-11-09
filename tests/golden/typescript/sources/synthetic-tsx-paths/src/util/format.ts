export const SEPARATOR = ", ";

export function join(parts: string[]): string {
  return parts.join(SEPARATOR);
}

export type Label = { text: string };
