import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, posix, resolve, win32 } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const repository = resolve(packageRoot, "../..");
const uvCache = process.env.UV_CACHE_DIR ?? join(tmpdir(), "archkeel-uv-cache");

function fixture(t, files, config = {}) {
  const root = mkdtempSync(join(tmpdir(), "archkeel-ts-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const contents = {
    "tsconfig.json": JSON.stringify({ compilerOptions: { module: "NodeNext", moduleResolution: "NodeNext" }, include: ["src"], ...config }),
    ...files,
  };
  for (const [path, value] of Object.entries(contents)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), value);
  }
  return root;
}

function request(root, roots = ["src"]) {
  return { protocol_version: "1.0.0", snapshot: { root, git_head: "a".repeat(40), dirty: false }, scope: { roots, namespace: "app" }, resolver: { language: "typescript", tsconfig: "tsconfig.json" } };
}

function invoke(input) {
  return spawnSync(process.execPath, [join(packageRoot, "dist/entry.js")], { input: typeof input === "string" ? input : JSON.stringify(input), encoding: "utf8" });
}

function collect(input) {
  const result = invoke(input);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function records(response, section) {
  return response.facts.sections.find(item => item.name === section).records;
}

test("indirect module.require cannot claim complete dependency coverage", t => {
  const sources = [
    "module.require.call(module, './hidden.cjs');\n",
    "const load = module.require; load('./hidden.cjs');\n",
    "const load = module.require; load.call(module, './hidden.cjs');\n",
    "module['require'].apply(module, ['./hidden.cjs']);\n",
  ];
  for (const source of sources) {
    const root = fixture(t, { "src/main.ts": source, "src/hidden.cjs": "module.exports = 7;\n" });
    const facts = collect(request(root)).facts;
    const observed = facts.sections.find(item => item.name === "imports").records.some(item => item.data.specifier === "./hidden.cjs");
    assert.ok(observed || (!facts.coverage.full_scope && facts.coverage.gaps.length > 0), source);
  }
  const root = fixture(t, { "src/main.ts": "require('./hidden.cjs');\n", "src/hidden.cjs": "module.exports = 7;\n" });
  const control = collect(request(root));
  assert.equal(control.facts.coverage.full_scope, true);
  assert.ok(records(control, "imports").some(item => item.data.specifier === "./hidden.cjs"));
});

test("real compiler resolves aliases, import forms and CJS runtime closure", t => {
  const root = fixture(t, {
    "src/main.ts": `import type { Value } from "@app/value";\nexport { value } from "./value.js";\nexport * from "./extra.js";\ntype Loaded = import("./value.js").Value;\nimport("./extra.js");\nimport host = require("./host.cjs");\nconst x = require("./host.cjs");\n`,
    "src/value.ts": "export interface Value { value: string }\nexport const value = 1;\n",
    "src/extra.ts": "export const extra = 1;\n",
    "src/host.d.cts": "declare const host: string[]; export = host;\n",
    "src/host.cjs": "const os = require('node:os'); module.exports = [os.platform()];\n",
  }, { compilerOptions: { module: "NodeNext", moduleResolution: "NodeNext", baseUrl: ".", paths: { "@app/*": ["src/*"] } }, include: ["src"] });
  const output = collect(request(root));
  assert.equal(output.facts.profile, "archkeel-typescript-imports");
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.ok(output.facts.files.some(item => item.rel_path === "src/host.cjs"));
  assert.ok(output.facts.imports.some(item => item.kind === "builtin" && item.name === "node:os"));
  assert.ok(output.facts.imports.some(item => item.kind === "local" && item.runtime_file === "src/host.cjs" && item.declaration_file === "src/host.d.cts"));
  assert.ok(records(output, "imports").some(item => item.data.type_only));
  for (const item of records(output, "imports")) {
    assert.equal(item.data.relative_level, 0);
    assert.equal(item.data.under_type_checking, item.data.type_only);
  }
  assert.deepEqual(output, collect(request(root)));
});

test("selected scope is distinct from resolution-only inputs", t => {
  const root = fixture(t, { "src/main.ts": "import '../shared/value.js';\n", "shared/value.ts": "export const value = 1;\n", "test/other.ts": "import 'missing';\n" }, { include: ["src", "test"] });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.inputs.some(item => item.path === "shared/value.ts" && item.role === "resolution"));
  assert.ok(!output.facts.files.some(item => item.rel_path.startsWith("test/") || item.rel_path.startsWith("shared/")));
  assert.ok(output.facts.coverage.gaps.length > 0);
});

test("computed, shadowed and unresolved imports leave explicit gaps", t => {
  const root = fixture(t, { "src/main.ts": "require(variable);\nfunction f(require: Function) { require('./missing.js'); }\nimport './not-here.js';\nimport(name);\n" });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.length >= 4);
  assert.ok(output.facts.imports.some(item => item.kind === "unresolved"));
});

test("syntax and config errors cannot claim complete coverage", t => {
  const root = fixture(t, { "src/main.ts": "const = ;\n", "tsconfig.json": '{"extends":"../absent.json","include":["src"]}' });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.length >= 2);
});

test("source-only protocol rejects policy, traversal and duplicate keys", t => {
  const root = fixture(t, { "src/main.ts": "export {};\n" });
  for (const input of [{ ...request(root), contract: {} }, request(root, ["../escape"]), JSON.stringify(request(root)).replace('"protocol_version":"1.0.0"', '"protocol_version":"1.0.0","protocol_version":"1.0.0"')]) {
    const result = invoke(input);
    assert.notEqual(result.status, 0);
    assert.equal(result.stdout, "");
  }
});

test("actual Python decoder accepts Node SourceFacts", t => {
  const root = fixture(t, { "src/main.ts": "import './value.js';\n", "src/value.ts": "export const value = 1;\n" });
  const output = invoke(request(root));
  assert.equal(output.status, 0, output.stderr);
  const decoded = spawnSync("uv", ["run", "--locked", "python", "-c", "import sys; from archkeel.ir.facts_codec import decode_response; facts = decode_response(sys.stdin.buffer.read()).facts; assert facts.profile == 'archkeel-typescript-imports'; assert facts.coverage.full_scope"], { cwd: repository, input: output.stdout, encoding: "utf8", env: { ...process.env, UV_CACHE_DIR: uvCache } });
  assert.equal(decoded.status, 0, decoded.stderr);
});

test("declarations do not substitute for missing runtime implementations", t => {
  const root = fixture(t, { "src/main.ts": "import host = require('./host.cjs');", "src/host.d.cts": "declare const host: string; export = host;" });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("Runtime implementation unavailable")));
  assert.ok(output.facts.imports.some(item => item.declaration_file === "src/host.d.cts" && item.runtime_file === null));
});

test("type-only named imports avoid inventing declaration runtime requirements", t => {
  const root = fixture(t, { "src/main.ts": "import { type Value } from './value.js'; export { type Value } from './value.js';", "src/value.d.ts": "export interface Value { value: string }" });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.ok(records(output, "imports").every(item => item.data.type_only));
});

test("ESM require, indirect require and triple-slash references are unknown", t => {
  const root = fixture(t, { "src/main.mts": "/// <reference path='./other.d.ts' />\nconst load = require; require('node:fs'); load(name);", "src/other.d.ts": "export {};" });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("Indirect require")));
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("Unproven or shadowed")));
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("triple-slash")));
  assert.equal(output.facts.imports.length, 0);
});

test("resolved external package identity is bound to its in-snapshot inputs", t => {
  const root = fixture(t, {
    "src/main.ts": "import 'example';",
    "node_modules/example/package.json": '{"name":"example","version":"1.0.0","types":"index.d.ts"}',
    "node_modules/example/index.d.ts": "export {};",
  });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.ok(output.facts.imports.some(item => item.kind === "external" && item.package === "example"));
  assert.ok(output.facts.inputs.some(item => item.path === "node_modules/example/package.json"));
  assert.ok(output.facts.inputs.some(item => item.path === "node_modules/example/index.d.ts"));
});

test("local JS closure is parsed, never executed", t => {
  const root = fixture(t, { "src/main.ts": "import './runtime.js';", "src/runtime.js": "throw new Error('must not execute'); import './leaf.js';", "src/leaf.js": "import 'node:fs';" });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.ok(output.facts.files.some(item => item.rel_path === "src/leaf.js"));
  assert.ok(output.facts.imports.some(item => item.kind === "builtin"));
});

test("missing inputs, project references, and malformed requests never look complete", t => {
  const root = fixture(t, { "src/main.ts": "export {};" }, { references: [{ path: "../generated" }], include: ["src"] });
  assert.equal(collect(request(root)).facts.coverage.full_scope, false);
  const missing = request(root); missing.resolver.tsconfig = "missing.json";
  assert.equal(collect(missing).facts.coverage.full_scope, false);
  for (const roots of [["src", "src/nested"], ["src", "src/"], [".", "src"], []]) assert.notEqual(invoke(request(root, roots)).status, 0);
});

test("shared protocol schema and strict Core decoder accept actual output", t => {
  const root = fixture(t, { "src/main.ts": "import 'node:fs';" });
  const output = invoke(request(root));
  const script = `import json, pathlib, sys\nimport jsonschema\nfrom archkeel.ir.facts_codec import decode_response\npayload = sys.stdin.buffer.read()\nfacts = decode_response(payload).facts\nschema = json.loads(pathlib.Path('schema/source-facts.schema.json').read_text())\njsonschema.Draft202012Validator(schema).validate(json.loads(payload))\nassert facts.runtime.name == 'node'\nassert facts.adapter.version == '1.0.0+typescript.5.9.3'\n`;
  const decoded = spawnSync("uv", ["run", "--locked", "python", "-c", script], { cwd: repository, input: output.stdout, encoding: "utf8", env: { ...process.env, UV_CACHE_DIR: uvCache } });
  assert.equal(decoded.status, 0, decoded.stderr);
});

test("shared request fixtures and identity cases agree with the adapter", async () => {
  const { decodeRequest, moduleIdentity } = await import("../dist/protocol.js");
  const valid = readFileSync(join(repository, "tests/fixtures/collection-protocol/request-typescript.json"), "utf8");
  assert.equal(decodeRequest(valid).resolver.language, "typescript");
  const invalid = readFileSync(join(repository, "tests/fixtures/collection-protocol/invalid-request-policy.json"), "utf8");
  assert.throws(() => decodeRequest(invalid));
  const identityPath = process.env.ARCHKEEL_IDENTITY_FIXTURE ?? join(repository, "fixtures/language-module-identities.json");
  const cases = JSON.parse(readFileSync(identityPath, "utf8"));
  for (const example of cases.filter(item => item.language === "typescript")) assert.equal(moduleIdentity(example.namespace, example.path), example.module);
  const paths = ["src/foo.ts", "src/foo.js", "src/foo.test.ts", "src/foo/test.ts", "src/foo/index.ts", "src/a_b.ts", "src/a-b.ts", "src/_x2e_.ts", "src/@scope/name.ts"];
  assert.equal(new Set(paths.map(path => moduleIdentity("app", path))).size, paths.length);
});

test("local require declarations and computed CommonJS access cannot prove imports", t => {
  const root = fixture(t, { "src/main.ts": "function require(name: string) { return name; } require('./leaf.js'); module['require']('./leaf.js');", "src/leaf.ts": "export {};" });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.equal(output.facts.imports.length, 0);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("Computed require member")));
});


test("resolver symlinks outside the snapshot remain unknown and undigested", t => {
  const outside = fixture(t, { "src/private.ts": "export const privateValue = 1;" });
  const root = fixture(t, { "src/main.ts": "import './private.js';" });
  symlinkSync(join(outside, "src/private.ts"), join(root, "src/private.ts"));
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("symlink outside")));
  assert.ok(!output.facts.inputs.some(item => item.path === "src/private.ts"));
});

test("package declarations do not prove a neighboring runtime target", t => {
  const root = fixture(t, {
    "src/main.ts": "import pkg = require('./pkg');",
    "src/pkg/package.json": '{"types":"types/index.d.ts","main":"runtime/entry.cjs"}',
    "src/pkg/types/index.d.ts": "declare const value: number; export = value;",
    "src/pkg/types/index.js": "module.exports = 1;",
    "src/pkg/runtime/entry.cjs": "require('../hidden.cjs');",
    "src/pkg/hidden.cjs": "require('../main.js');",
  }, { files: ["src/main.ts"], include: [] });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("Runtime implementation unavailable")));
  assert.ok(output.facts.imports.every(item => item.runtime_file !== "src/pkg/types/index.js"));
  assert.ok(!output.facts.files.some(item => item.rel_path === "src/pkg/types/index.js"));
});

test("explicit missing TSConfig files remain selected with a gap", t => {
  const root = fixture(t, { "src/main.ts": "export {};" }, { files: ["src/main.ts", "src/missing.ts"], include: [] });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.deepEqual(output.facts.coverage.selected_files, ["src/main.ts", "src/missing.ts"]);
  assert.equal(output.facts.coverage.files_read, 1);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("src/missing.ts")));
});

test("Node createRequire aliases leave unsupported loader coverage unknown", t => {
  const root = fixture(t, { "src/main.mts": "import { createRequire as factory } from 'node:module'; const load = factory(import.meta.url); load('./hidden.cjs');", "src/hidden.cjs": "require('./main.mjs');" }, { files: ["src/main.mts"], include: [] });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("createRequire")));
  for (const source of [
    "import * as mod from 'node:module'; const load = mod.createRequire(import.meta.url);",
    "const { createRequire: factory } = require('node:module'); const load = factory(__filename);",
    "const factory = require('node:module').createRequire; const load = factory(__filename);",
  ]) {
    const variant = fixture(t, { "src/main.ts": source });
    assert.ok(collect(request(variant)).facts.coverage.gaps.some(item => item.title.includes("createRequire")));
  }
  const plain = fixture(t, { "src/main.ts": "function createRequire(x: string) { return x; } createRequire('data');" });
  assert.equal(collect(request(plain)).facts.coverage.full_scope, true);
});

test("bare builtin names respect compiler-resolved local type aliases", t => {
  const root = fixture(t, { "src/main.ts": "import type { Value } from 'fs'; import 'node:fs';", "src/local.ts": "export type Value = string;" }, { compilerOptions: { module: "ESNext", moduleResolution: "Bundler", baseUrl: ".", paths: { fs: ["src/local.ts"] } }, files: ["src/main.ts"], include: [] });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.ok(output.facts.imports.some(item => item.kind === "local" && item.file === "src/local.ts"));
  assert.ok(output.facts.imports.some(item => item.kind === "builtin" && item.name === "node:fs"));
});

test("original compiler option diagnostics become coverage gaps", t => {
  const root = fixture(t, { "src/main.ts": "export {};" }, { compilerOptions: { module: "CommonJS", moduleResolution: "NodeNext" } });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("5110")));
  const valid = fixture(t, { "src/main.ts": "export {};" }, { compilerOptions: { module: "NodeNext", moduleResolution: "NodeNext", lib: ["ES2022"], types: [] } });
  assert.equal(collect(request(valid)).facts.coverage.full_scope, true);
});

test("per-import resolution mode selects the compiler's matching package condition", t => {
  for (const [source, expected] of [
    ['type T = import("#target", { with: { "resolution-mode": "require" } }).Value;', "src/require.ts"],
    ['import type { Value } from "#target" with { "resolution-mode": "require" };', "src/require.ts"],
    ['import type { Value } from "#target" with { "resolution-mode": "import" };', "src/import.ts"],
    ['import type { Value } from "#target";', "src/import.ts"],
  ]) {
    const root = fixture(t, {
      "package.json": JSON.stringify({ type: "module", imports: { "#target": { import: "./src/import.ts", require: "./src/require.ts" } } }),
      "src/main.mts": source, "src/import.ts": "export interface Value { a: string }", "src/require.ts": "export interface Value { b: string }",
    }, { files: ["src/main.mts"], include: [] });
    const output = collect(request(root));
    assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
    assert.equal(output.facts.imports.length, 1);
    assert.equal(output.facts.imports[0].file, expected);
    assert.ok(output.facts.files.some(item => item.rel_path === expected));
    assert.ok(output.facts.inputs.some(item => item.path === "package.json"));
    assert.ok(records(output, "imports").every(item => item.data.under_type_checking));
  }
});

test("JSDoc import types and import tags observe their type-only closure", t => {
  for (const comment of ['/** @typedef {import("./hidden.js").Value} Value */', '/** @import {Value} from "./hidden.js" */']) {
    const root = fixture(t, { "src/main.js": comment + "\nexport const x = 1;", "src/hidden.js": "import './missing.js'; export const Value = 1;" }, { compilerOptions: { module: "NodeNext", moduleResolution: "NodeNext", allowJs: true, checkJs: true }, files: ["src/main.js"], include: [] });
    const output = collect(request(root));
    assert.equal(output.facts.coverage.full_scope, false);
    assert.ok(output.facts.files.some(item => item.rel_path === "src/hidden.js"));
    assert.equal(output.facts.imports.filter(item => item.kind === "local" && item.file === "src/hidden.js").length, 1);
    assert.ok(records(output, "imports").some(item => item.data.source_module.endsWith("main_x2e_js") && item.data.under_type_checking));
    assert.ok(output.facts.imports.some(item => item.kind === "unresolved" && item.specifier === "./missing.js"));
    assert.deepEqual(output, collect(request(root)));
    writeFileSync(join(root, "src/hidden.js"), "export const Value = 1;");
    const complete = collect(request(root));
    assert.equal(complete.facts.coverage.full_scope, true, JSON.stringify(complete.facts.coverage.gaps));
    assert.notEqual(complete.facts.source.source_digest, output.facts.source.source_digest);
  }
});

test("Node module bracket loader access is incomplete, including computed names", t => {
  for (const access of ["mod['createRequire']", "mod[key]"]) {
    const root = fixture(t, { "src/main.mts": `import * as mod from 'node:module'; const load = ${access}(import.meta.url); load('./hidden.cjs');`, "src/hidden.cjs": "require('./main.mjs');" }, { files: ["src/main.mts"], include: [] });
    const output = collect(request(root));
    assert.equal(output.facts.coverage.full_scope, false);
    assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("createRequire")));
  }
  const root = fixture(t, { "src/main.mts": "import * as mod from 'node:module'; mod['isBuiltin']('node:fs'); const plain = { createRequire() { return 1; } }; plain['createRequire']();" });
  assert.equal(collect(request(root)).facts.coverage.full_scope, true);
});


test("external package symlinks outside the snapshot remain incomplete", t => {
  const outside = fixture(t, { "pkg/package.json": '{"name":"example","version":"1.0.0","types":"index.d.ts"}', "pkg/index.d.ts": "export {};" });
  const root = fixture(t, { "src/main.ts": "import 'example';" });
  mkdirSync(join(root, "node_modules"));
  symlinkSync(join(outside, "pkg"), join(root, "node_modules/example"));
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("symlink outside")));
  assert.ok(output.facts.imports.some(item => item.kind === "unresolved"));
  assert.ok(!output.facts.inputs.some(item => item.path.startsWith("node_modules/")));
});

test("selected workspace symlinks stay local and expose their dependency closure", t => {
  const root = fixture(t, {
    "src/main.ts": "import 'example';",
    "src/shared/package.json": '{"name":"example","version":"1.0.0","types":"index.ts"}',
    "src/shared/index.ts": "import './hidden.js';",
    "src/shared/hidden.ts": "import './missing.js';",
  }, { compilerOptions: { module: "NodeNext", moduleResolution: "NodeNext", preserveSymlinks: false }, files: ["src/main.ts"], include: [] });
  mkdirSync(join(root, "node_modules"));
  symlinkSync("../src/shared", join(root, "node_modules/example"));
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.imports.some(item => item.kind === "local" && item.file === "src/shared/index.ts"));
  assert.ok(!output.facts.imports.some(item => item.kind === "external" && item.package === "example"));
  assert.ok(output.facts.files.some(item => item.rel_path === "src/shared/index.ts"));
  assert.ok(output.facts.files.some(item => item.rel_path === "src/shared/hidden.ts"));
  assert.ok(output.facts.imports.some(item => item.kind === "unresolved" && item.specifier === "./missing.js"));
  assert.ok(output.facts.inputs.some(item => item.path === "src/shared/index.ts" && item.role === "selected"));
  writeFileSync(join(root, "src/shared/hidden.ts"), "export const value = 1;");
  assert.equal(collect(request(root)).facts.coverage.full_scope, true);
});

test("preserved symlink lookup context cannot emit a canonical-path dependency", async t => {
  const ts = (await import("typescript")).default;
  const root = fixture(t, {
    "src/main.ts": "import 'example';",
    "src/shared/package.json": '{"name":"example","version":"1.0.0","types":"index.ts"}',
    "src/shared/index.ts": "import 'dep';",
    "src/node_modules/dep/package.json": '{"name":"dep","version":"1.0.0","types":"index.ts"}',
    "src/node_modules/dep/index.ts": "export const version = 1;",
    "node_modules/dep/package.json": '{"name":"dep","version":"2.0.0","types":"index.ts"}',
    "node_modules/dep/index.ts": "export const version = 2;",
  }, { compilerOptions: { module: "NodeNext", moduleResolution: "NodeNext", preserveSymlinks: true }, files: ["src/main.ts"], include: [] });
  symlinkSync("../src/shared", join(root, "node_modules/example"));
  const options = { module: ts.ModuleKind.NodeNext, moduleResolution: ts.ModuleResolutionKind.NodeNext, preserveSymlinks: true };
  const fromAlias = ts.resolveModuleName("dep", join(root, "node_modules/example/index.ts"), options, ts.sys).resolvedModule;
  const fromRealPath = ts.resolveModuleName("dep", join(root, "src/shared/index.ts"), options, ts.sys).resolvedModule;
  assert.equal(fromAlias.packageId.version, "2.0.0");
  assert.equal(fromRealPath.packageId.version, "1.0.0");
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.coverage.gaps.some(item => item.title.includes("preserveSymlinks")));
  assert.deepEqual(output.facts.files.map(item => item.rel_path), ["src/main.ts"]);
  assert.equal(output.facts.imports.length, 1);
  assert.equal(output.facts.imports[0].kind, "unresolved");
  assert.equal(output.facts.imports[0].specifier, "example");
  assert.ok(!output.facts.inputs.some(item => item.path === "src/node_modules/dep/index.ts"));
});

test("request snapshot roots accept native absolute paths, while relative paths stay POSIX", async () => {
  const { decodeRequest } = await import("../dist/protocol.js");
  const windowsRoot = win32.join("C:", win32.sep, "repo");
  for (const root of ["/repo", "/", windowsRoot, "C:/repo", String.raw`\\server\share\repo`]) {
    const input = request(root, ["src/app"]);
    input.resolver.tsconfig = "config/tsconfig.json";
    const decoded = decodeRequest(JSON.stringify(input));
    assert.equal(decoded.snapshot.root, root);
    assert.deepEqual(decoded.scope.roots, ["src/app"]);
    assert.equal(decoded.resolver.tsconfig, "config/tsconfig.json");
  }
  for (const root of ["repo", "C:repo", "C:", String.raw`\repo`, String.raw`\\server`, windowsRoot + "/mixed", String.raw`/repo\mixed`, ""]) {
    assert.throws(() => decodeRequest(JSON.stringify(request(root))), undefined, root);
  }
  const invalidScope = request(windowsRoot, [String.raw`src\app`]);
  assert.throws(() => decodeRequest(JSON.stringify(invalidScope)));
  const invalidConfig = request(windowsRoot);
  invalidConfig.resolver.tsconfig = String.raw`config\tsconfig.json`;
  assert.throws(() => decodeRequest(JSON.stringify(invalidConfig)));
});


test("source containment follows platform path rules", async () => {
  const { withinRoot } = await import("../dist/project.js");
  const windowsScope = win32.join("C:", win32.sep, "repo", "src");
  for (const [platform, scope, path, expected] of [
    [posix, "/repo/src", "/repo/src/main.ts", true],
    [posix, "/repo/src", "/repo/src", true],
    [posix, "/repo/src", "/repo/src2/main.ts", false],
    [posix, "/repo/src", "/repo/src/../other/main.ts", false],
    [win32, windowsScope, "C:/repo/src/main.ts", true],
    [win32, windowsScope, windowsScope, true],
    [win32, windowsScope, windowsScope + String.raw`2\main.ts`, false],
    [win32, windowsScope, windowsScope + String.raw`\..\other\main.ts`, false],
    [win32, windowsScope, String.raw`D:\repo\src\main.ts`, false],
    [win32, String.raw`\\server\share\src`, String.raw`\\server\share\src\main.ts`, true],
    [win32, String.raw`\\server\share\src`, String.raw`\\server\other\src\main.ts`, false],
  ]) assert.equal(withinRoot(scope, path, platform), expected, `${scope}: ${path}`);
});

test("explicit file roots preserve runtime and declaration closure and literal scope", t => {
  const root = fixture(t, {
    "src/main.ts": "import hosts = require('../supportedHosts.cjs');",
    "supportedHosts.cjs": "module.exports = [require('node:os').platform()];",
    "supportedHosts.d.cts": "declare const hosts: readonly string[]; export = hosts;",
    "unselected.ts": "import './missing.js';",
  });
  const output = collect(request(root, ["src", "supportedHosts.cjs", "supportedHosts.d.cts"]));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.deepEqual(output.facts.source.scope, ["src/**", "supportedHosts.cjs", "supportedHosts.d.cts"]);
  assert.deepEqual(output.facts.files.map(file => file.rel_path), ["src/main.ts", "supportedHosts.cjs", "supportedHosts.d.cts"]);
});

test("repository-wide scope keeps installed dependencies external", t => {
  const root = fixture(t, {
    "src/main.ts": "import type { Thing } from 'lib'; import { value } from 'lib'; export const use: Thing = value;",
    "node_modules/lib/package.json": '{"name":"lib","version":"1.0.0","types":"index.d.ts","main":"index.js"}',
    "node_modules/lib/index.d.ts": "export interface Thing { n: number }; export declare const value: Thing;",
    "node_modules/lib/index.js": "exports.value = { n: 1 };",
  }, { include: ["src/**/*.ts"], exclude: ["node_modules"] });
  for (const roots of [["src"], ["."]]) {
    const output = collect(request(root, roots));
    assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
    assert.deepEqual(output.facts.files.map(file => file.rel_path), ["src/main.ts"]);
    assert.deepEqual(output.facts.imports.map(target => [target.kind, target.package]), [["external", "lib"], ["external", "lib"]]);
    assert.ok(output.facts.inputs.some(input => input.path === "node_modules/lib/index.d.ts" && input.role === "resolution"));
  }
});

test("unreferenced explicit file roots are selected beyond tsconfig include and exclude", t => {
  const root = fixture(t, {
    "src/main.ts": "export {};",
    "standalone.cjs": "require('./missing.cjs');",
    "standalone.ts": "export const value = 1;",
  }, { include: ["src"], exclude: ["standalone.*"] });
  const positive = collect(request(root, ["standalone.ts"]));
  assert.equal(positive.facts.coverage.full_scope, true, JSON.stringify(positive.facts.coverage.gaps));
  assert.deepEqual(positive.facts.files.map(file => file.rel_path), ["standalone.ts"]);
  const missing = collect(request(root, ["src", "standalone.cjs"]));
  assert.equal(missing.facts.coverage.full_scope, false);
  assert.deepEqual(missing.facts.files.map(file => file.rel_path), ["src/main.ts", "standalone.cjs"]);
  assert.ok(missing.facts.imports.some(target => target.kind === "unresolved" && target.specifier === "./missing.cjs"));
});

test("Node module namespace loader factories remain unsupported", t => {
  for (const source of [
    "const mod = require('node:module'); const load = mod.createRequire(__filename); load('./missing.cjs');",
    "const mod = require('node:module'); const load = mod['createRequire'](__filename); load('./missing.cjs');",
    "const mod = require('node:module'); const { createRequire: factory } = mod; const load = factory(__filename); load('./missing.cjs');",
    "import mod = require('node:module'); const load = mod.createRequire(__filename); load('./missing.cjs');",
  ]) {
    const root = fixture(t, { "src/main.cts": source });
    const output = collect(request(root));
    assert.equal(output.facts.coverage.full_scope, false, source);
    assert.ok(output.facts.coverage.gaps.some(gap => gap.title.includes("createRequire")), source);
  }
  const root = fixture(t, { "src/main.cts": "const local = {createRequire: () => 1}; local.createRequire();" });
  assert.equal(collect(request(root)).facts.coverage.full_scope, true);
});

test("tsconfig cannot select installed node_modules declarations as local graph files", t => {
  const root = fixture(t, {
    "src/main.ts": "import type { Value } from 'example';",
    "node_modules/example/package.json": '{"name":"example","version":"1.0.0","types":"index.d.ts"}',
    "node_modules/example/index.d.ts": "export interface Value { value: string };",
  }, { include: ["src", "node_modules/example/**/*.ts"], exclude: [] });
  const output = collect(request(root, ["."]));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.deepEqual(output.facts.files.map(file => file.rel_path), ["src/main.ts"]);
  assert.deepEqual(output.facts.coverage.selected_files, ["src/main.ts"]);
  assert.equal(output.facts.imports[0].kind, "external");
  assert.ok(output.facts.inputs.some(input => input.path === "node_modules/example/index.d.ts" && input.role === "resolution"));
  const explicit = collect(request(root, ["src", "node_modules/example/index.d.ts"]));
  assert.equal(explicit.facts.coverage.full_scope, false);
  assert.deepEqual(explicit.facts.files.map(file => file.rel_path), ["src/main.ts"]);
  assert.ok(explicit.facts.coverage.gaps.some(gap => gap.title.includes("Installed dependency")));
});

test("external runtime API identity stays distinct from its declaration provider", t => {
  const root = fixture(t, {
    "package.json": '{"name":"app","imports":{"#local":"./src/local.ts"}}',
    "src/main.ts": "import type { Uri } from 'vscode'; import type { Feature } from '@vendor/host/feature'; import '#local';",
    "src/local.ts": "export {};",
    "node_modules/@types/vscode/package.json": '{"name":"@types/vscode","version":"1.0.0","types":"index.d.ts"}',
    "node_modules/@types/vscode/index.d.ts": "export interface Uri { path: string };",
    "node_modules/@types/vendor__host/package.json": '{"name":"@types/vendor__host","version":"1.0.0","types":"index.d.ts"}',
    "node_modules/@types/vendor__host/feature.d.ts": "export interface Feature { name: string };",
  });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, true, JSON.stringify(output.facts.coverage.gaps));
  assert.deepEqual(output.facts.imports.filter(target => target.kind === "external").map(target => target.package), ["vscode", "@vendor/host"]);
  assert.ok(output.facts.imports.some(target => target.kind === "local" && target.file === "src/local.ts"));
  const imports = records(output, "imports");
  for (const [specifier, runtime] of [["vscode", "vscode"], ["@vendor/host/feature", "@vendor/host"]]) {
    const record = imports.find(record => record.data.specifier === specifier);
    assert.equal(record.data.target_module, runtime);
    assert.equal(record.data.target_package, runtime);
  }
  assert.ok(output.facts.inputs.some(input => input.path === "node_modules/@types/vscode/index.d.ts" && input.role === "resolution"));
});

test("external package import aliases cannot inherit declaration-provider identity", t => {
  const root = fixture(t, {
    "package.json": '{"name":"app","imports":{"#host":"host-api","#local":"./src/local.ts"}}',
    "src/main.ts": "import { value } from '#host'; import '#local';",
    "src/local.ts": "export {};",
    "src/host.ts": "export {};",
    "node_modules/host-api/package.json": '{"name":"host-api","version":"1.0.0","main":"index.js"}',
    "node_modules/host-api/index.js": "exports.value = 1;",
    "node_modules/@types/host-api/package.json": '{"name":"@types/host-api","version":"1.0.0","types":"index.d.ts"}',
    "node_modules/@types/host-api/index.d.ts": "export declare const value: number;",
  });
  const output = collect(request(root));
  assert.equal(output.facts.coverage.full_scope, false);
  assert.ok(output.facts.imports.some(target => target.kind === "unresolved" && target.specifier === "#host"));
  assert.ok(output.facts.coverage.gaps.some(gap => gap.title.includes("External package alias identity is not observed: #host")));
  assert.ok(!output.facts.imports.some(target => target.kind === "external"));
  assert.ok(output.facts.imports.some(target => target.kind === "local" && target.file === "src/local.ts"));
  writeFileSync(join(root, "archkeel.toml"), `[scan]\nroots=["src"]\nnamespace="app"\ncontract="architecture-contract.json"\nlanguage="typescript"\ntsconfig="tsconfig.json"\ncollector_argv=${JSON.stringify([process.execPath, join(packageRoot, "dist/entry.js")])}\n`);
  writeFileSync(join(root, "architecture-contract.json"), JSON.stringify({ schema_version: "2.1.0", components: [], rules: [{ id: "HOST-API-SCOPE", kind: "external_dependency_scope", dependency: "host-api", exact_sources: ["app.src.host_x2e_ts"], rationale: "Only the host module owns the external host API.", provenance: ["architecture.md"], decided_by: "agent" }] }));
  writeFileSync(join(root, "architecture.md"), "The host module owns host-api.\n");
  for (const args of [["init", "-q"], ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "snapshot"]]) {
    const result = spawnSync("git", args, { cwd: root, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
  }
  for (const external of [true, false]) {
    if (!external) writeFileSync(join(root, "src/main.ts"), "import '#local';");
    const result = spawnSync("uv", ["run", "--locked", "archkeel", "report", "--root", root, "--json"], { cwd: repository, encoding: "utf8", env: { ...process.env, UV_CACHE_DIR: uvCache } });
    assert.equal(result.status, external ? 2 : 0, result.stderr || result.stdout);
    const report = JSON.parse(result.stdout);
    assert.equal(report.observation_complete, external ? "UNKNOWN" : "PASS");
    assert.equal(report.declared_rules, external ? "UNKNOWN" : "PASS");
  }
});
