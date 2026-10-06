// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT
// Capture the bounded TSConfig corpus with: node fixtures/capture_typescript_config_reference.cjs /path/to/typescript.js
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const ts = require(process.argv[2]);

if (ts.version !== "5.9.3") throw new Error(`Expected TypeScript 5.9.3, got ${ts.version}`);

const sources = Object.fromEntries(
  [
    "src/main.ts", "src/main.js", "src/loose.js", "src/excluded.ts",
    "src/base-build/gen.ts", "src/base-types/gen.d.ts", "src/root-build/gen.ts",
    "src/root-types/gen.d.ts", "src/left-build/gen.ts", "src/right-types/gen.d.ts",
    "src/override/keep.ts", "src/override/drop.ts", "src/other/extra.ts",
  ].map((file) => [file, "export {};\n"]),
);
const base = {
  compilerOptions: { outDir: "../src/base-build", declarationDir: "../src/base-types" },
  include: ["../src"],
};
const right = {
  compilerOptions: { declarationDir: "../src/right-types" },
  include: ["../src"],
};
const checkJs = { compilerOptions: { checkJs: true }, include: ["../src"] };
const shared = {
  ...sources,
  "configs/base.json": JSON.stringify(base),
  "configs/left.json": JSON.stringify(base),
  "configs/right.json": JSON.stringify(right),
  "configs/check-js.json": JSON.stringify(checkJs),
};
const cases = {};
function add(name, config, files = {}) {
  cases[name] = { files: { ...shared, ...files, "tsconfig.json": JSON.stringify(config) }, roots: ["src"], tsconfig: "tsconfig.json" };
}

add("inherited_outputs_from_extended_config", { extends: "./configs/base.json" });
add("root_out_dir_override_retains_inherited_declaration_dir", { extends: "./configs/base.json", compilerOptions: { outDir: "src/root-build" } });
add("root_declaration_dir_override_retains_inherited_out_dir", { extends: "./configs/base.json", compilerOptions: { declarationDir: "src/root-types" } });
add("root_overrides_both_output_dirs", { extends: "./configs/base.json", compilerOptions: { outDir: "src/root-build", declarationDir: "src/root-types" } });
add("later_extends_entry_overrides_only_declaration_dir", { extends: ["./configs/left.json", "./configs/right.json"] });
add("root_include_override_is_relative_to_root_config", { extends: "./configs/base.json", include: ["src/override"] });
add("root_exclude_override_replaces_default_exclude", { extends: "./configs/base.json", exclude: [] });
add("inherited_exclude_is_relative_to_extended_config", { extends: "./configs/exclude.json" }, {
  "configs/exclude.json": JSON.stringify({ ...base, exclude: ["../src/excluded.ts"] }),
});
add("root_include_and_exclude_overrides", { extends: "./configs/base.json", include: ["src/override"], exclude: ["src/override/drop.ts"] });
add("local_check_js_without_allow_js", { compilerOptions: { checkJs: true }, include: ["src"] });
add("local_check_js_with_allow_js_null", { compilerOptions: { checkJs: true, allowJs: null }, include: ["src"] });
add("inherited_check_js_without_allow_js", { extends: "./configs/check-js.json" });
add("inherited_check_js_with_allow_js_null", { extends: "./configs/check-js.json", compilerOptions: { allowJs: null } });
for (const [name, config] of [
  ["compiler_options_string", { compilerOptions: "oops", include: ["src"] }],
  ["out_dir_number", { compilerOptions: { outDir: 7 }, include: ["src"] }],
  ["declaration_dir_boolean", { compilerOptions: { declarationDir: false }, include: ["src"] }],
  ["allow_js_string", { compilerOptions: { allowJs: "false" }, include: ["src"] }],
  ["base_url_boolean", { compilerOptions: { baseUrl: true }, include: ["src"] }],
  ["module_number", { compilerOptions: { module: 3 }, include: ["src"] }],
  ["module_resolution_array", { compilerOptions: { moduleResolution: [] }, include: ["src"] }],
  ["target_object", { compilerOptions: { target: {} }, include: ["src"] }],
  ["resolve_json_module_string", { compilerOptions: { resolveJsonModule: "true" }, include: ["src"] }],
  ["files_string", { files: "src/main.ts" }],
  ["include_string", { include: "src" }],
  ["exclude_object", { include: ["src"], exclude: { src: true } }],
]) add(`invalid_${name}`, config);

const canonical = (value) => Array.isArray(value)
  ? `[${value.map(canonical).join(",")}]`
  : value && typeof value === "object"
    ? `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`
    : JSON.stringify(value);
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "archkeel-tsconfig-reference-"));
try {
  const captured = {};
  for (const [name, input] of Object.entries(cases)) {
    const root = path.join(temporary, name);
    for (const [relative, content] of Object.entries(input.files)) {
      const file = path.join(root, relative);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, content);
    }
    const configPath = path.join(root, input.tsconfig);
    const config = ts.readConfigFile(configPath, ts.sys.readFile).config;
    const parsed = ts.parseJsonConfigFileContent(config, ts.sys, root, undefined, configPath);
    const selected = parsed.fileNames
      .map((file) => path.relative(root, file).split(path.sep).join("/"))
      .filter((file) => input.roots.some((basePath) => file === basePath || file.startsWith(`${basePath}/`)))
      .sort();
    const diagnostics = parsed.errors.map((diagnostic) => ({
      code: diagnostic.code,
      message: ts.flattenDiagnosticMessageText(diagnostic.messageText, " ").replaceAll(root, "<root>"),
    }));
    const fingerprint = crypto.createHash("sha256").update(canonical(input)).digest("hex");
    captured[name] = { ...input, input_digest: fingerprint, selected, diagnostics };
  }
  const output = {
    schema_version: 1,
    reference: { producer: "TypeScript Compiler API", version: ts.version, method: "parseJsonConfigFileContent", diagnostics: "parsed.errors" },
    cases: captured,
  };
  fs.writeFileSync(path.join(__dirname, "typescript-config-reference.json"), `${JSON.stringify(output, null, 2)}\n`);
  console.log(`Captured ${Object.keys(captured).length} TSConfig cases with TypeScript ${ts.version}.`);
} finally {
  fs.rmSync(temporary, { recursive: true, force: true });
}
