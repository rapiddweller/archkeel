"use strict";
/** @param {ArchkeelBrowser.Origin} value @returns {boolean} */
function isObserved(value) {
  return value === ArchkeelBrowser.Origin.OBSERVED;
}
const origin = ArchkeelBrowser.decodeOrigin("observed");
const assessment = ArchkeelBrowser.decodeAssessment("PASS");
if (!isObserved(origin)) throw new Error("Nominal control failed");
if (assessment !== ArchkeelBrowser.Assessment.PASS) throw new Error("Assessment failed");
if (JSON.stringify({origin: ArchkeelBrowser.encodeOrigin(origin)}) !== '{"origin":"observed"}') throw new Error("Wire changed");
for (const raw of [null, 0, {}, [], "missing", "PASS"]) {
  let rejected = false;
  try { ArchkeelBrowser.decodeOrigin(raw); } catch { rejected = true; }
  if (!rejected) throw new Error("Unknown origin accepted");
}
