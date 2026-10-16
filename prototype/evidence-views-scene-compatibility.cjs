"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const root = "src/archkeel/render/assets/";
function load(sources) {
  const sandbox = {window:{},structuredClone,console};
  vm.createContext(sandbox);
  for (const source of sources) vm.runInContext(source, sandbox);
  return sandbox.window.ArchkeelReportScene;
}
const old = load([fs.readFileSync(process.argv[2],"utf8")]);
const current = load(["report-graph-protocol.js","report-graph-scene.js","report-scene.js"]
  .map(name => fs.readFileSync(root+name,"utf8")));
const graph = {origin:"observed",entities:[
  {id:"a",kind:"module",qualified_name:"pkg.a",parent_id:null,presence:"defined",
   responsibilities:[],modifiers:[],file_path:"pkg/a.py"},
  {id:"b",kind:"module",qualified_name:"pkg.b",parent_id:null,presence:"defined",
   responsibilities:[],modifiers:[],file_path:"pkg/b.py"}],
  relationships:[{id:"i",kind:"imports",source_id:"a",target_id:"b",
    candidate_ids:[],resolution:"resolved"}],component_intents:[]};
function compare(api, options) {
  const data = structuredClone({observed:graph,target:null});
  const model = api.create(data);
  const context = {graph:data.observed,scope:null,comparison:null};
  const explicit = model.projectArchitectureScene(context,{viewMode:"diagram",
    directChildren:options?.directChildren ?? false});
  const implicit = options === undefined ? model.projectArchitectureScene(context)
    : model.projectArchitectureScene(context,options);
  assert.deepEqual(implicit,explicit);
  return true;
}
const controls = [];
for (const options of [undefined,{}, {directChildren:true}, {viewMode:undefined}]) {
  compare(old,options);
  let failure = null;
  try { compare(current,options); } catch (error) { failure=String(error); }
  controls.push({case: ["omitted", "empty", "direct-children-only", "explicit-undefined"][controls.length],
    options: options ?? "omitted", old_default_matches_explicit_diagram:true,
    new_failure:failure});
}
console.log("REAL_LEGACY_OPTION_PARITY=" + JSON.stringify(controls));
assert(controls.every(control => control.new_failure === null),"New source lost a valid legacy default");

function explicitScene(api,viewMode) {
  const data = structuredClone({observed:graph,target:null});
  const model = api.create(data);
  return JSON.stringify(model.projectArchitectureScene(
    {graph:data.observed,scope:null,comparison:null},{viewMode}));
}
const evidence = [];
for (const viewMode of ["actual","structure","review"]) {
  const before = explicitScene(old,viewMode);
  let after = null, failure = null;
  try { after = explicitScene(current,viewMode); } catch(error) { failure=String(error); }
  evidence.push({viewMode,old_valid:!!before,new_failure:failure,wire_equal:before===after});
}
console.log("REAL_EXISTING_EVIDENCE_VIEW_PARITY=" + JSON.stringify(evidence));
assert(evidence.every(control=>control.wire_equal),"New Scene rejected existing visible Evidence modes");
