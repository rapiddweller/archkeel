"use strict";
/** @param {SceneProbe.Origin} value @returns {boolean} */
function isObserved(value) { return value === SceneProbe.Origin.OBSERVED; }
const rawGraph = {origin: "observed", id: "sample.any-user-data"};
const decoded = SceneProbe.graph(rawGraph);
if (decoded !== rawGraph) throw new Error("Graph was copied");
if (!isObserved(decoded.origin)) throw new Error("Origin decision failed");
if (JSON.stringify(decoded) !== '{"origin":"observed","id":"sample.any-user-data"}') throw new Error("Wire changed");
const clone = structuredClone(decoded);
if (clone.origin !== SceneProbe.Origin.OBSERVED) throw new Error("Clone lost primitive");
for (const invalid of [null, 0, {}, [], "missing", "PASS", SceneProbe.Assessment.PASS]) {
  let rejected = false;
  try { SceneProbe.decodeOrigin(invalid); } catch { rejected = true; }
  if (!rejected) throw new Error("Unknown origin accepted");
}
console.log("Identity, exact JSON, structuredClone and unknown rejection pass");
