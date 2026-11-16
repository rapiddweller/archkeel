"use strict";
// Own the recorded deviation rows and their actual level/pair classification.
var ArchkeelAtlasDeviations = (function () {
  const G = ArchkeelGraphProtocol;
  const P = ArchkeelGraphSceneProtocol;
  /** @param {string} source @param {string} target */
  const pairKey = (source, target) => `${source}\0${target}`;
  /** @param {unknown} value */
  function create(value) {
    /** @type {Map<string | null, Map<string, ArchkeelGraphSceneProtocol.AtlasDeviation>>} */
    const levels = new Map();
    for (const row of P.decodeAtlasDeviations(value)) {
      let level = levels.get(row.level_id);
      if (!level) {
        level = new Map();
        levels.set(row.level_id, level);
      }
      level.set(pairKey(row.source_id, row.target_id), row);
    }
    /** @param {string | null} levelId @param {string} source @param {string} target @returns {boolean} */
    function isUndeclared(levelId, source, target) {
      return levels.get(levelId)?.get(pairKey(source, target))?.kind === G.AtlasDeviationKind.UNDECLARED;
    }
    /** @param {string | null} levelId @returns {readonly ArchkeelGraphSceneProtocol.AtlasDeviation[]} */
    function unused(levelId) {
      return [...(levels.get(levelId)?.values() || [])]
        .filter((row) => row.kind === G.AtlasDeviationKind.ALLOWED_UNUSED);
    }
    return { isUndeclared, unused };
  }
  return { create };
})();
