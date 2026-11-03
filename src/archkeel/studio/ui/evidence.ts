/** AD-290: the evidence model. Decide on these values, never on a label text. */
export const Evidence = {
  Observed: "observed",
  Claim: "claim",
  Target: "target",
} as const;
export type Evidence = (typeof Evidence)[keyof typeof Evidence];

export interface EvidenceKind {
  readonly evidence: Evidence;
  readonly name: string;
  readonly meaning: string;
}

/** In legend order; the CSS class of each kind is its value. */
export const EVIDENCE: readonly EvidenceKind[] = [
  { evidence: Evidence.Observed, name: "Observed", meaning: "code evidence" },
  { evidence: Evidence.Claim, name: "Claim", meaning: "agent hypothesis" },
  { evidence: Evidence.Target, name: "Target", meaning: "architect decision" },
];
