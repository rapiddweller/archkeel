"use strict";
// AD-290: the Studio bundle; Preact resolves from the locked tools, not from the tsconfig paths.
const path = require("node:path");
const esbuild = require("esbuild");
const ui = path.resolve(__dirname, "../../src/archkeel/studio/ui");
esbuild.build({
  entryPoints: [path.join(ui, "shell.tsx")],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2022",
  minify: true,
  jsx: "automatic",
  jsxImportSource: "preact",
  legalComments: "inline",
  nodePaths: [path.join(__dirname, "node_modules")],
  tsconfigRaw: "{}",
  write: false,
}).then(result => process.stdout.write(result.outputFiles[0].contents)).catch(() => process.exit(1));
