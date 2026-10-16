namespace SceneProbe {
  export enum Origin { OBSERVED = "observed", DECLARED = "declared" }
  export enum Assessment { PASS = "PASS", FAIL = "FAIL", UNKNOWN = "UNKNOWN" }
  export enum RuleAssessment { PASS = "PASS", FAIL = "FAIL", UNKNOWN = "UNKNOWN", DECLARATION = "DECLARATION" }
  enum JavaScriptType { OBJECT = "object", STRING = "string" }
  const origins: ReadonlyMap<unknown, Origin> = new Map([
    ["observed", Origin.OBSERVED], ["declared", Origin.DECLARED],
  ]);
  export function decodeOrigin(raw: unknown): Origin {
    const token = origins.get(raw);
    if (token === undefined) throw new TypeError("Unsupported origin");
    return token;
  }
  export interface Graph { origin: Origin; id: string }
  export function graph(raw: unknown): Graph {
    if (!isGraph(raw)) throw new TypeError("Unsupported graph");
    return raw;
  }
  function isRecord(raw: unknown): raw is Record<string, unknown> {
    return typeof raw === JavaScriptType.OBJECT && raw !== null && !Array.isArray(raw);
  }
  function isOrigin(raw: unknown): raw is Origin { return origins.has(raw); }
  function isGraph(raw: unknown): raw is Graph {
    return isRecord(raw) && isOrigin(raw.origin) && typeof raw.id === JavaScriptType.STRING;
  }
}
