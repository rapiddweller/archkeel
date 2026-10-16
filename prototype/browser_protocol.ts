namespace ArchkeelBrowser {
  export enum Origin { OBSERVED, TARGET }
  export enum Assessment { PASS, FAIL, UNKNOWN }
  const origins: ReadonlyMap<unknown, Origin> = new Map([
    ["observed", Origin.OBSERVED],
    ["target", Origin.TARGET],
  ]);
  const assessments: ReadonlyMap<unknown, Assessment> = new Map([
    ["PASS", Assessment.PASS],
    ["FAIL", Assessment.FAIL],
    ["UNKNOWN", Assessment.UNKNOWN],
  ]);
  const originWire: ReadonlyMap<Origin, string> = new Map([
    [Origin.OBSERVED, "observed"],
    [Origin.TARGET, "target"],
  ]);
  export function decodeOrigin(raw: unknown): Origin {
    const value = origins.get(raw);
    if (value === undefined) throw new TypeError("Unsupported origin");
    return value;
  }
  export function decodeAssessment(raw: unknown): Assessment {
    const value = assessments.get(raw);
    if (value === undefined) throw new TypeError("Unsupported assessment");
    return value;
  }
  export function encodeOrigin(value: Origin): string {
    const wire = originWire.get(value);
    if (wire === undefined) throw new TypeError("Unsupported origin token");
    return wire;
  }
}
