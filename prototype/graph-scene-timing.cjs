const fs = require("fs");
const vm = require("vm");
const {performance} = require("perf_hooks");
const payload = fs.readFileSync(process.argv[2], "utf8");
const before = fs.readFileSync(process.argv[3], "utf8");
const assetRoot = "src/archkeel/render/assets/";
function environment(sources) {
  const sandbox = {window:{},structuredClone,console};
  vm.createContext(sandbox);
  for (const source of sources) vm.runInContext(source,sandbox);
  return sandbox.window.ArchkeelReportScene;
}
const previous = environment([before]);
const current = environment(["report-graph-protocol.js","report-graph-scene.js","report-scene.js"]
  .map(name => fs.readFileSync(assetRoot+name,"utf8")));
function summary(scene) {
  return JSON.stringify(scene,(key,value) => key === "sourceGraph" ? {origin:value.origin} : value);
}
function sample(api) {
  const data = JSON.parse(payload);
  const original = JSON.stringify(data);
  const graph = data.observed;
  const module = graph.entities.find(entity => entity.kind === "module"
    && entity.qualified_name === "archkeel.ir.architecture_graph");
  const start = performance.now();
  const model = api.create(data);
  const created = performance.now();
  const context = {graph,scope:module.id,comparison:null};
  const options = {viewMode:"diagram"};
  const scene = model.projectArchitectureScene(context,options);
  const first = performance.now();
  const repeats=[];
  for(let i=0;i<5;i+=1){
    const t=performance.now(); model.projectArchitectureScene(context,options);
    repeats.push(performance.now()-t);
  }
  const wire = JSON.stringify(data);
  if(original!==wire)throw new Error("Input graph mutated");
  if(!scene.nodes.every(node=>node.sourceGraph===graph&&graph.entities.includes(node.entity)))
    throw new Error("Graph/entity identity changed");
  return {create_ms:created-start,first_projection_ms:first-created,
    repeat_projection_ms:repeats.sort((a,b)=>a-b)[2],scene:summary(scene),
    mermaid:api.sceneToMermaid(scene),cards:scene.nodes.length,
    nodes:graph.entities.length,relationships:graph.relationships.length};
}
const oldSamples=[],newSamples=[];
for(let i=0;i<5;i+=1){oldSamples.push(sample(previous));newSamples.push(sample(current));}
for(let i=0;i<oldSamples.length;i+=1){
  if(oldSamples[i].scene!==newSamples[i].scene)throw new Error("Before/after full scene values changed");
  if(oldSamples[i].mermaid!==newSamples[i].mermaid)throw new Error("Before/after Mermaid changed");
}
const median=(samples,key)=>samples.map(value=>value[key]).sort((a,b)=>a-b)[2];
console.log("SCENE_PERFORMANCE="+JSON.stringify({
  same_payload_bytes:Buffer.byteLength(payload),
  entities:newSamples[0].nodes,relationships:newSamples[0].relationships,cards:newSamples[0].cards,
  before:{create_ms:median(oldSamples,"create_ms"),first_projection_ms:median(oldSamples,"first_projection_ms"),
    repeat_projection_ms:median(oldSamples,"repeat_projection_ms")},
  after:{create_ms:median(newSamples,"create_ms"),first_projection_ms:median(newSamples,"first_projection_ms"),
    repeat_projection_ms:median(newSamples,"repeat_projection_ms")},
  full_scene_and_mermaid_equal:true,original_input_and_graph_entity_identity:true,
}));
