"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const modules = process.argv[2];
const terser = require(path.join(modules, "terser"));
const acorn = require(path.join(modules, "acorn"));
const root = "src/archkeel/render/assets";
function canonical(value, taggedTemplate = false) {
  if (Array.isArray(value)) return value.map(item => canonical(item, taggedTemplate));
  if (typeof value === "bigint") return {bigint: value.toString()};
  if (value === null || typeof value !== "object") return value;
  const result = {};
  for (const [key, item] of Object.entries(value)) {
    if (key === "start" || key === "end" || key === "raw" && value.type === "Literal") continue;
    if (value.type === "TemplateElement" && key === "value" && !taggedTemplate) {
      result[key] = {cooked: item.cooked};
      continue;
    }
    const taggedChild = value.type === "TaggedTemplateExpression" && key === "quasi"
      || taggedTemplate && value.type === "TemplateLiteral" && key === "quasis";
    result[key] = canonical(item, taggedChild);
  }
  return result;
}
function ast(code) {
  return JSON.stringify(canonical(acorn.parse(code, {ecmaVersion: 2022, sourceType: "script"})));
}
const assert = require("node:assert/strict");
assert.equal(ast("\\u0060a\\nb\\u0060"), ast("\\u0060a\\\\nb\\u0060"));
assert.notEqual(ast("tag\\u0060a\\nb\\u0060"), ast("tag\\u0060a\\\\nb\\u0060"));
for (const [before, after] of [[\'"object"\', \'"string"\'], ["/a/", "/b/"], ["value", "other"], ["({a:1})", "({b:1})"]]) {
  assert.notEqual(ast(before), ast(after));
}
(async () => {
  const sizes = [];
  for (const file of fs.readdirSync(root).filter(file => file.endsWith(".js") && !file.startsWith("elkjs-"))) {
    const filePath = path.join(root, file);
    const original = fs.readFileSync(filePath, "utf8");
    const options = {ecma: 2022, compress: false, mangle: false, keep_fnames: true, keep_classnames: true,
      format: {comments: false, beautify: false, semicolons: true, keep_quoted_props: true}};
    const first = await terser.minify({[file]: original}, options);
    const second = await terser.minify({[file]: original}, options);
    if (first.code !== second.code) throw new Error("Non-deterministic print: " + file);
    const before = ast(original);
    const after = ast(first.code);
    if (before !== after) {
      fs.writeFileSync("ast-before.json", before);
      fs.writeFileSync("ast-after.json", after);
      const index = [...before].findIndex((character, index) => character !== after[index]);
      throw new Error("AST change " + file + " at " + index + ": " + before.slice(index, index+400) + " VS " + after.slice(index,index+400));
    }
    fs.writeFileSync(filePath, first.code + "\n");
    sizes.push({file, before: Buffer.byteLength(original), after: Buffer.byteLength(first.code+"\n"),
      ast_sha256: crypto.createHash("sha256").update(before).digest("hex"), deterministic: true});
  }
  console.log("AUXILIARY_PRINT_ONLY=" + JSON.stringify({terser:"5.44.0", acorn:"8.15.0", compress:false,
    mangle:false, comments:false, original_ast_preserved:true, sizes}));
})().catch(error => { console.error(error); process.exitCode = 1; });
