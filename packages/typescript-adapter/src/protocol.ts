import { createHash } from "node:crypto";
import { posix, win32 } from "node:path";

export interface Request {
  protocol_version: "1.0.0";
  snapshot: { root: string; git_head: string; dirty: boolean | "unknown" };
  scope: { roots: string[]; namespace: string };
  resolver: { language: "typescript"; tsconfig: string };
}
export interface SourceRecord {
  id: string; evidence_class: "FACT" | "UNKNOWN"; area: string; kind: string;
  title: string; subjects: string[]; evidence_ids: string[]; rule_ids: never[];
  fact_ids: string[]; provenance: never[]; data: { [key: string]: unknown };
}
export interface Evidence { id: string; file: string; line: number; end_line: number; column: number; excerpt: string }
export type Target =
  | { kind: "local"; import_id: string; module: string; file: string; runtime_file: string | null; declaration_file: string | null }
  | { kind: "builtin"; import_id: string; name: string }
  | { kind: "external"; import_id: string; package: string }
  | { kind: "unresolved"; import_id: string; specifier: string; reason: string };
export const digest = (value: string | Buffer): string => createHash("sha256").update(value).digest("hex");
export const id = (prefix: string, ...parts: (string | number)[]): string => `${prefix}-${digest(parts.join("\x1f")).slice(0, 16)}`;
export function moduleIdentity(namespace: string, path: string): string {
  return [namespace, ...path.split("/").map(segment => Array.from(segment).map((char, index) =>
    /^[A-Za-z0-9]$/.test(char) && !(index === 0 && /^[0-9]$/.test(char)) ? char : `_x${char.codePointAt(0)?.toString(16)}_`).join(""))].join(".");
}
function object(value: unknown, fields: string[]): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value) || Object.keys(value).sort().join() !== fields.sort().join()) throw Error("request fields mismatch");
  return Object.fromEntries(Object.entries(value));
}
function string(value: unknown): string {
  if (typeof value !== "string" || !value || value.includes("\0")) throw Error("expected nonempty string");
  return value;
}
function relative(value: unknown): string {
  const path = string(value);
  if (path.startsWith("/") || /[\\:]/.test(path) || path.split("/").includes("..")) throw Error("path escapes snapshot");
  return path;
}
// JSON.parse discards duplicate fields, so inspect keys before parsing their values.
function rejectDuplicates(text: string): void {
  const tokens = text.match(/"(?:[^"\\]|\\.)*"|[{}\[\]:,]|[^\s{}\[\]:,]+/g) ?? [];
  let index = 0;
  function value(): void {
    const token = tokens[index++];
    if (token === "{") {
      const keys = new Set<string>();
      while (tokens[index] !== "}") {
        const key: unknown = JSON.parse(tokens[index++] ?? "");
        if (typeof key !== "string" || keys.has(key)) throw Error("duplicate or invalid JSON key");
        keys.add(key);
        if (tokens[index++] !== ":") throw Error("invalid JSON");
        value();
        if (tokens[index] !== ",") break;
        index++;
      }
      if (tokens[index++] !== "}") throw Error("invalid JSON");
    } else if (token === "[") {
      while (tokens[index] !== "]") {
        value();
        if (tokens[index] !== ",") break;
        index++;
      }
      if (tokens[index++] !== "]") throw Error("invalid JSON");
    }
  }
  value();
}
export function decodeRequest(text: string): Request {
  rejectDuplicates(text);
  const value: unknown = JSON.parse(text);
  const raw = object(value, ["protocol_version", "snapshot", "scope", "resolver"]);
  if (raw.protocol_version !== "1.0.0") throw Error("unsupported protocol version");
  const snapshot = object(raw.snapshot, ["root", "git_head", "dirty"]);
  const root = string(snapshot.root);
  const posixAbsolute = posix.isAbsolute(root) && !root.includes("\\");
  const windowsAbsolute = win32.isAbsolute(root) && win32.parse(root).root.length > 1
    && !(root.includes("\\") && root.includes("/"));
  if (!posixAbsolute && !windowsAbsolute) throw Error("snapshot root must be an absolute native path");
  const dirty = snapshot.dirty;
  if (typeof dirty !== "boolean" && dirty !== "unknown") throw Error("invalid dirty status");
  const scope = object(raw.scope, ["roots", "namespace"]);
  if (!Array.isArray(scope.roots) || !scope.roots.length) throw Error("missing source roots");
  const roots = scope.roots.map(relative);
  const normalized = roots.map(path => path.split("/").filter(part => part && part !== ".").join("/"));
  if (normalized.some((path, index) => normalized.some((other, j) => index !== j && (path === other || !other || path.startsWith(other + "/"))))) throw Error("source roots overlap");
  const namespace = string(scope.namespace);
  if (!/^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(namespace)) throw Error("invalid namespace");
  const resolver = object(raw.resolver, ["language", "tsconfig"]);
  if (resolver.language !== "typescript") throw Error("unsupported language");
  return { protocol_version: "1.0.0", snapshot: { root, git_head: string(snapshot.git_head), dirty }, scope: { roots, namespace }, resolver: { language: "typescript", tsconfig: relative(resolver.tsconfig) } };
}
