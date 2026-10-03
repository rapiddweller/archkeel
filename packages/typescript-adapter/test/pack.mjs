import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const temp = mkdtempSync(join(tmpdir(), "archkeel-package-"));
const npmEntry = process.env.npm_execpath;
assert.ok(npmEntry && isAbsolute(npmEntry), "Run this gate through npm run test:pack");
function run(command, args, cwd, input) {
  // Empty PATH proves that package checks never need an npm executable or .cmd shim.
  const result = spawnSync(command, args, { cwd, input, encoding: "utf8", env: { ...process.env, PATH: "" } });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout;
}
try {
  const [packed] = JSON.parse(run(process.execPath, [npmEntry, "pack", "--ignore-scripts", "--json", "--pack-destination", temp], root));
  const paths = packed.files.map(file => file.path);
  for (const name of ["entry", "project", "collect", "protocol"]) assert.ok(paths.includes(`dist/${name}.js`));
  assert.ok(paths.includes("README.md"));
  assert.ok(paths.includes(".node-version"));
  assert.ok(!paths.some(path => path.startsWith("src/") || path.startsWith("test/") || path.startsWith("node_modules/")));
  const consumer = join(temp, "consumer");
  mkdirSync(consumer);
  writeFileSync(join(consumer, "package.json"), JSON.stringify({ private: true, dependencies: { "@archkeel/typescript-adapter": `file:${join(temp, packed.filename)}` } }));
  run(process.execPath, [npmEntry, "install", "--package-lock-only", "--ignore-scripts", "--no-audit"], consumer);
  run(process.execPath, [npmEntry, "ci", "--ignore-scripts", "--offline", "--no-audit"], consumer);
  const fixture = join(temp, "fixture");
  mkdirSync(join(fixture, "src"), { recursive: true });
  writeFileSync(join(fixture, "tsconfig.json"), '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext"},"include":["src"]}');
  writeFileSync(join(fixture, "src", "main.ts"), "import './value.js';");
  writeFileSync(join(fixture, "src", "value.ts"), "export const value = 1;");
  const request = { protocol_version: "1.0.0", snapshot: { root: fixture, git_head: "unknown", dirty: false }, scope: { roots: ["src"], namespace: "app" }, resolver: { language: "typescript", tsconfig: "tsconfig.json" } };
  const output = JSON.parse(run(process.execPath, [join(consumer, "node_modules", "@archkeel", "typescript-adapter", "dist", "entry.js")], dirname(fixture), JSON.stringify(request)));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.equal(output.facts.runtime.version, process.versions.node);
  assert.equal(typeof output.facts.runtime.required, "string");
  assert.deepEqual(output.facts.capabilities.constructs, []);
  assert.equal(output.facts.files.length, 2);
  console.log("Packed artifact: isolated offline install, locked npm ci, and collection passed");
} finally {
  rmSync(temp, { recursive: true, force: true });
}
