"use strict";
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const modules = path.resolve(process.argv[2]);
const acorn = require(path.join(modules,"acorn"));
const walk = require(path.join(modules,"acorn-walk"));
function semanticAst(source) {
  const tree = acorn.parse(source,{ecmaVersion:2022,sourceType:"script"});
  const tagged = new WeakSet();
  walk.simple(tree,{TaggedTemplateExpression(node) { tagged.add(node.quasi); }});
  walk.simple(tree,{
    Literal(node) { delete node.raw; },
    Property(node) { if (!node.computed) delete node.key.raw; },
    MethodDefinition(node) { if (!node.computed) delete node.key.raw; },
    PropertyDefinition(node) { if (!node.computed) delete node.key.raw; },
    TemplateLiteral(node) {
      if (!tagged.has(node)) {
        for (const quasi of node.quasis) quasi.value = {cooked:quasi.value.cooked};
      }
    },
  });
  const locations = new Set(["start","end"]);
  return JSON.stringify(tree,(key,value) => locations.has(key) ? undefined : value);
}
const tick = String.fromCharCode(96);
const actualLineBreak = tick+"a"+String.fromCharCode(10)+"b"+tick;
const escapedLineBreak = tick+"a\\nb"+tick;
assert.equal(semanticAst(actualLineBreak),semanticAst(escapedLineBreak));
assert.notEqual(semanticAst("tag"+actualLineBreak),semanticAst("tag"+escapedLineBreak));
for (const [before,after] of [
  ['"object"','"string"'],["/a/","/b/"],["value","other"],["({a:1})","({b:1})"],
  ["function one(){}","function two(){}"],["class One{}","class Two{}"],
]) assert.notEqual(semanticAst(before),semanticAst(after));
const source = fs.readFileSync(process.argv[3],"utf8");
const emitted = fs.readFileSync(process.argv[4],"utf8");
const before = semanticAst(source);
const after = semanticAst(emitted);
assert(after === before,"Published Flow must preserve the actual program AST");
console.log("FLOW_SEMANTIC_AST="+JSON.stringify({
  source_bytes:Buffer.byteLength(source),emitted_bytes:Buffer.byteLength(emitted),
  sha256:crypto.createHash("sha256").update(before).digest("hex"),
  tagged_raw_preserved:true,negative_controls:7,
}));
