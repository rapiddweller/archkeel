"use strict";
/** @param {ArchkeelBrowser.Origin} value @returns {boolean} */
function isObserved(value) {
  return value === ArchkeelBrowser.Origin.OBSERVED;
}
const decodedOrigin = ArchkeelBrowser.decodeOrigin("observed");
const decodedAssessment = ArchkeelBrowser.decodeAssessment("PASS");
if (!isObserved(decodedOrigin)) throw new Error("Nominal control failed");
if (decodedAssessment !== ArchkeelBrowser.Assessment.PASS) throw new Error("Assessment failed");
if (JSON.stringify({origin: ArchkeelBrowser.encodeOrigin(decodedOrigin)}) !== '{"origin":"observed"}') throw new Error("Wire changed");
for (const raw of [null, 0, {}, [], "missing", "PASS"]) {
  let rejected = false;
  try { ArchkeelBrowser.decodeOrigin(raw); } catch { rejected = true; }
  if (!rejected) throw new Error("Unknown origin accepted");
}
