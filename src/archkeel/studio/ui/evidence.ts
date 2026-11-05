/** AD-290: the evidence model. Decide on these values, never on a label text. */
import { CheckStatus } from "./api";

export const Evidence = {
  Observed: "observed",
  Claim: "claim",
  Target: "target",
} as const;
export type Evidence = (typeof Evidence)[keyof typeof Evidence];

interface EvidenceKind {
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

/** The proof of one call: a glyph and a word, never a colour alone. */
export const Proof = {
  Proven: "proven",
  Claim: "claim",
  Unknown: "unknown",
} as const;
export type Proof = (typeof Proof)[keyof typeof Proof];

/** A check has five statuses; only proven is proven when shown as a three-part proof. */
const PROOF_OF_CHECK: Readonly<Record<CheckStatus, Proof>> = {
  [CheckStatus.Proven]: Proof.Proven,
  [CheckStatus.Declared]: Proof.Claim,
  [CheckStatus.Claim]: Proof.Claim,
  [CheckStatus.Unknown]: Proof.Unknown,
  [CheckStatus.Missing]: Proof.Unknown,
};

export const proofOfCheck = (status: CheckStatus): Proof => PROOF_OF_CHECK[status];

interface ProofKind {
  readonly proof: Proof;
  readonly glyph: string;
  readonly word: string;
  readonly meaning: string;
}

/** In legend order; the CSS class of each kind is its value. */
export const PROOF: readonly ProofKind[] = [
  { proof: Proof.Proven, glyph: "✓", word: "proven", meaning: "resolved call" },
  { proof: Proof.Claim, glyph: "✎", word: "claim", meaning: "partly resolved call" },
  { proof: Proof.Unknown, glyph: "?", word: "unknown", meaning: "no target found" },
];

/** A resolved call is proven; a partly resolved call is a claim. */
export const proofOf = (partial: boolean): typeof Proof.Proven | typeof Proof.Claim => (partial ? Proof.Claim : Proof.Proven);

/** The one rule for two calls between the same functions: a resolved call wins over a partial one. */
export const better = (known: { readonly partial: boolean } | undefined, now: { readonly partial: boolean }): boolean =>
  known === undefined || (known.partial && !now.partial);

export const proofKind = (proof: Proof): ProofKind => PROOF.find((kind) => kind.proof === proof) ?? PROOF[0];
