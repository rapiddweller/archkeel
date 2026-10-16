"use strict";
/** @type {SceneProbe.Graph} */
const invalidRawField = {origin: "observed", id: "raw"};
/** @type {SceneProbe.Graph} */
const invalidCrossDomainField = {origin: SceneProbe.Assessment.PASS, id: "cross"};
/** @returns {string} */
function widenedReturn() { return SceneProbe.Origin.OBSERVED; }
/** @type {SceneProbe.Origin} */
const invalidReturn = widenedReturn();
