// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bind an amendment to one `--against` comparison, as Python `_widening_failures`,
//! `verify_amendment` and `_before_digest` (`check/validation/__init__.py`, `ir/amendment.py`) do.
//!
//! An amendment covers a comparison when its four digests equal the digests of this comparison:
//! the comparison digest of the old tree (or the digest of no contract at the old path), the
//! comparison digest of the new tree, and the digests of the old and the new baseline. A covered
//! comparison passes with each widening. An amendment that does not bind fails, also when nothing
//! widened. A `Verdict` comes only from `Binding::check`, a `Binding` only from `bind`, and `bind`
//! takes assembled trees only (AD-375).

use crate::contract::digest_of;
use crate::policy::amendment::{
    computed_digest, nonempty_text, Amendment, AmendmentDigest, AmendmentError, AmendmentField,
};
use crate::policy::change::{ChangeDirection, ChangeKind, ContractChange};
use crate::policy::compare::{compare_trees, Comparison};
use crate::policy::tree::ContractTree;

/// The failure of a stale amendment where no change widened (Python `_widening_failures`).
const NOT_BOUND: &str = "amendment does not bind this contract and baseline comparison";

/// The old side of `--against`: an assembled tree, or no contract at `path` at the revision
/// `against` (AD-104). The shell decides that the revision holds no blob at `path`; the crate
/// makes the change and the digest of it.
#[derive(Clone, Copy, Debug)]
pub enum OldContract<'a> {
    Tree(&'a ContractTree),
    Introduced { path: &'a str, against: &'a str },
}

/// The baseline fact of the run, which the shell must state (lead decision L-34a). Python binds
/// the digests of the old and the new baseline, and it computes them from the baseline content.
/// The crate has no baseline codec yet (M6b row 2), so a run with `--baseline` gets no binding:
/// `bind` refuses it. A digest text from the caller is never accepted (AD-375).
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub struct Baselines {
    state: BaselineState,
}

#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
enum BaselineState {
    NotConfigured,
    ConfiguredUnsupported,
    #[cfg(test)]
    Bound(AmendmentDigest, AmendmentDigest),
}

impl Baselines {
    /// The run has no `--baseline`: the amendment must hold `null` for both baseline digests.
    pub fn not_configured() -> Baselines {
        Baselines {
            state: BaselineState::NotConfigured,
        }
    }

    /// The run has a `--baseline`. `bind` refuses it with `BindError::BaselineNotSupported`.
    pub fn configured_unsupported() -> Baselines {
        Baselines {
            state: BaselineState::ConfiguredUnsupported,
        }
    }

    /// Two baseline digests, for the tests of the binding. The baseline codec replaces it with a
    /// constructor from the baseline that the crate writes.
    #[cfg(test)]
    pub(crate) fn bound(before: &str, after: &str) -> Baselines {
        Baselines {
            state: BaselineState::Bound(computed_digest(before), computed_digest(after)),
        }
    }

    /// The two baseline digests that an amendment must hold; `None` for a run without baseline.
    fn pair(&self) -> Option<(&AmendmentDigest, &AmendmentDigest)> {
        match &self.state {
            #[cfg(test)]
            BaselineState::Bound(before, after) => Some((before, after)),
            BaselineState::NotConfigured | BaselineState::ConfiguredUnsupported => None,
        }
    }
}

/// Why `bind` gives no binding.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BindError {
    /// The run has a `--baseline`, and the crate cannot compute its digests yet (L-34a).
    BaselineNotSupported,
}

impl std::fmt::Display for BindError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BindError::BaselineNotSupported => formatter
                .write_str("the Rust core cannot bind an amendment for a run with --baseline yet"),
        }
    }
}

impl std::error::Error for BindError {}

/// What the amendment gate says about one comparison.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum GateStatus {
    /// No change widened and no amendment was given.
    Unchanged,
    /// The amendment binds this comparison (Python `AmendmentStatus.VALID`). It covers each
    /// widening.
    Covered,
    /// A change widened and no amendment was given.
    Unamended,
    /// The amendment does not bind this comparison (Python `AmendmentStatus.STALE`).
    Stale,
}

record!(
    pub(crate),
    /// The decision of the gate and its failure messages, in the order of Python.
    Verdict {
        status: GateStatus,
        failures: Vec<String>,
    }
);

impl Verdict {
    /// Whether the gate passes: nothing widened, or a valid amendment covers the comparison.
    pub fn passes(&self) -> bool {
        matches!(self.status, GateStatus::Unchanged | GateStatus::Covered)
    }
}

record!(
    pub(crate),
    /// One comparison and the four digests that an amendment of it must hold.
    Binding {
        comparison: Comparison,
        before_digest: AmendmentDigest,
        after_digest: AmendmentDigest,
        baselines: Baselines,
    }
);

/// The digest that an amendment binds for no contract at `path` (Python `absent_contract_digest`):
/// no canonical contract begins with NUL.
pub(crate) fn absent_contract_digest(path: &str) -> String {
    let mut bytes = b"\0no contract at ".to_vec();
    bytes.extend_from_slice(path.as_bytes());
    digest_of(&bytes).0
}

/// The comparison when the old revision holds no contract at `path`: the whole contract is one
/// widening (Python `_contract_widening_findings` with `_Introduced`). No narrowing is named.
pub(crate) fn compare_introduced(path: &str, against: &str) -> Comparison {
    let message = format!("contract introduced: {path} does not exist at {against}");
    let subject = format!("contract {path}");
    let change = ContractChange::widened(ChangeKind::Presence, &subject, "presence", message);
    Comparison {
        changes: vec![change],
    }
}

/// Compare the old side with the new tree and keep the digests that an amendment must hold.
///
/// ```
/// use archkeel_contract::{parse, policy::{assemble_tree, bind, Baselines, OldContract}};
/// let bytes = br#"{"schema_version": "3.14.0", "components": [], "rules": []}"#;
/// let tree = assemble_tree("c.json", parse(bytes).unwrap(), &[]).unwrap();
/// let binding = bind(OldContract::Tree(&tree), &tree, Baselines::not_configured()).unwrap();
/// assert!(binding.check(None).passes());
/// let amendment = binding.amend("Jordan", "Accepted.").unwrap();
/// assert!(binding.check(Some(&amendment)).passes());
/// let with_baseline = Baselines::configured_unsupported();
/// assert!(bind(OldContract::Tree(&tree), &tree, with_baseline).is_err());
/// ```
///
/// A contract that is not an assembled tree cannot be bound:
///
/// ```compile_fail,E0308
/// use archkeel_contract::{parse, ParsedContract, policy::{bind, Baselines, OldContract}};
/// let bytes = br#"{"schema_version": "3.14.0", "components": [], "rules": []}"#;
/// let ParsedContract::Complete(contract) = parse(bytes).unwrap() else { return };
/// bind(OldContract::Tree(&contract), &contract, Baselines::not_configured());
/// ```
///
/// A verdict, a binding, an amendment and a digest cannot be written by hand. In each example
/// below the only error is a private field:
///
/// ```compile_fail,E0451
/// use archkeel_contract::policy::{GateStatus, Verdict};
/// let verdict = Verdict { status: GateStatus::Covered, failures: Vec::new() };
/// ```
///
/// ```compile_fail,E0451
/// use archkeel_contract::{parse, policy::{assemble_tree, bind, Baselines, Binding, OldContract}};
/// let bytes = br#"{"schema_version": "3.14.0", "components": [], "rules": []}"#;
/// let tree = assemble_tree("c.json", parse(bytes).unwrap(), &[]).unwrap();
/// let real = bind(OldContract::Tree(&tree), &tree, Baselines::not_configured()).unwrap();
/// let forged = Binding { after_digest: real.before_digest().clone(), ..real };
/// ```
///
/// ```compile_fail,E0451
/// use archkeel_contract::policy::{parse_amendment, Amendment};
/// let bytes = format!(r#"{{"schema_version": "2.0.0", "before_digest": "{0}",
///   "after_digest": "{0}", "decided_by": "a", "rationale": "b",
///   "before_baseline_digest": null, "after_baseline_digest": null}}"#, "0".repeat(64));
/// let real = parse_amendment(bytes.as_bytes()).unwrap();
/// let forged = Amendment { after_digest: real.before_digest().clone(), ..real };
/// ```
///
/// ```compile_fail,E0423
/// use archkeel_contract::policy::AmendmentDigest;
/// let digest = AmendmentDigest("0".repeat(64));
/// ```
pub fn bind(
    old: OldContract<'_>,
    after: &ContractTree,
    baselines: Baselines,
) -> Result<Binding, BindError> {
    if baselines.state == BaselineState::ConfiguredUnsupported {
        return Err(BindError::BaselineNotSupported);
    }
    let (comparison, before) = match old {
        OldContract::Tree(before) => (
            compare_trees(before, after),
            before.comparison_digest().as_text().to_owned(),
        ),
        OldContract::Introduced { path, against } => (
            compare_introduced(path, against),
            absent_contract_digest(path),
        ),
    };
    Ok(Binding {
        comparison,
        before_digest: computed_digest(&before),
        after_digest: computed_digest(after.comparison_digest().as_text()),
        baselines,
    })
}

impl Binding {
    /// Python `verify_amendment` for schema 2.0.0: the four digests are equal.
    fn binds(&self, amendment: &Amendment) -> bool {
        let (before_baseline, after_baseline) = match self.baselines.pair() {
            Some((before, after)) => (Some(before), Some(after)),
            None => (None, None),
        };
        *amendment.before_digest() == self.before_digest
            && *amendment.after_digest() == self.after_digest
            && amendment.before_baseline_digest().as_ref() == before_baseline
            && amendment.after_baseline_digest().as_ref() == after_baseline
    }

    /// Decide the gate for an amendment, or for none (Python `_widening_failures`).
    pub fn check(&self, amendment: Option<&Amendment>) -> Verdict {
        let messages: Vec<String> = self
            .comparison
            .changes()
            .iter()
            .filter(|change| *change.direction() == ChangeDirection::Widened)
            .map(|change| change.message().clone())
            .collect();
        let (status, failures) = match amendment {
            Some(amendment) if self.binds(amendment) => (GateStatus::Covered, Vec::new()),
            Some(_) if messages.is_empty() => (GateStatus::Stale, vec![NOT_BOUND.to_owned()]),
            Some(_) => (GateStatus::Stale, messages),
            None if messages.is_empty() => (GateStatus::Unchanged, messages),
            None => (GateStatus::Unamended, messages),
        };
        Verdict { status, failures }
    }

    /// The amendment that covers this comparison (Python `_artifact_files`). Rust refuses an
    /// empty or blank `decided_by` or `rationale`; Python writes it and then cannot read it.
    pub fn amend(&self, decided_by: &str, rationale: &str) -> Result<Amendment, AmendmentError> {
        let (before_baseline, after_baseline) = match self.baselines.pair() {
            Some((before, after)) => (Some(before.clone()), Some(after.clone())),
            None => (None, None),
        };
        Ok(Amendment {
            before_digest: self.before_digest.clone(),
            after_digest: self.after_digest.clone(),
            decided_by: nonempty_text(decided_by, AmendmentField::DecidedBy)?,
            rationale: nonempty_text(rationale, AmendmentField::Rationale)?,
            before_baseline_digest: before_baseline,
            after_baseline_digest: after_baseline,
        })
    }
}
