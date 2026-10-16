"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const acorn = require("./tools/browser-runtime/node_modules/acorn");
const walk = require("./tools/browser-runtime/node_modules/acorn-walk");
const scope = {};
vm.runInNewContext(fs.readFileSync("src/archkeel/render/assets/report-graph-protocol.js","utf8"),scope);
const domains = new Map();
for (const [name,domain] of Object.entries(scope.ArchkeelGraphProtocol)) {
  if (typeof domain === "object") for (const value of Object.values(domain)) {
    if (typeof value === "string") {
      const owners = domains.get(value) || [];
      owners.push(name); domains.set(value,owners);
    }
  }
}
for(const name of ["ViewMode","EdgeState","SceneEdgeKind"]) {
  for(const value of Object.values(scope.ArchkeelGraphSceneProtocol[name])) {
    const owners = domains.get(value) || []; owners.push(name); domains.set(value,owners);
  }
}
const paths = [
"src/archkeel/render/assets/flow.js",
"src/archkeel/render/assets/report-scene.js",
"src/archkeel/render/assets/report-graph-scene.js",
"src/archkeel/render/assets/report-canvas.js",
"src/archkeel/render/assets/report-layout.js",
"src/archkeel/render/assets/report-filters.js",
"src/archkeel/render/assets/violations.js",
];
const equals = new Set(["==","===","!=","!=="]);
const textMethods = new Set(["includes","startsWith","endsWith"]);
function literal(node) {
  if(node && typeof node.value === "string") return node.value;
  if(node && node.quasis && node.expressions.length === 0) return node.quasis[0].value.cooked;
  return null;
}
for(const path of paths) {
  const source=fs.readFileSync(path,"utf8");
  const ast=acorn.parse(source,{ecmaVersion:"latest",locations:true,sourceType:"script"});
  const entries=[];
  function record(node,other,token,form) {
    entries.push({line:node.loc.start.line,form,operand:source.slice(other.start,other.end),token,
      candidates:domains.get(token)||[]});
  }
  walk.simple(ast,{
    BinaryExpression(node) {
      if(!equals.has(node.operator)) return;
      const left=literal(node.left),right=literal(node.right);
      if(left !== null) record(node,node.right,left,node.operator);
      if(right !== null) record(node,node.left,right,node.operator);
    },
    SwitchCase(node) {
      const token=literal(node.test);
      if(token !== null) record(node,node.test,token,"switch-case");
    },
    CallExpression(node) {
      if(!node.callee.property || !textMethods.has(node.callee.property.name)) return;
      const token=literal(node.arguments[0]);
      if(token !== null) record(node,node.callee.object,token,node.callee.property.name);
      if(node.callee.object.elements) for(const entry of node.callee.object.elements) {
        const token=literal(entry);
        if(token !== null) record(node,node.arguments[0],token,"array-"+node.callee.property.name);
      }
    }
  });
  const counts = {};
  for(const entry of entries) counts[entry.form]=(counts[entry.form]||0)+1;
  console.log("BROWSER_CONTROL_INVENTORY="+JSON.stringify({path,bytes:Buffer.byteLength(source),counts,
    canonicalCandidates:entries.filter(entry=>entry.candidates.length).length,entries}));
}
