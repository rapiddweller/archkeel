// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one ordered list of the sources of doubt about a scope (AD-739). A rule and a whole run
//! read the same kinds of source; each subject has its fixed order, and the first source that holds
//! names the cause. `rule` (one rule) and `run` (the whole run) both walk this list, so a new
//! source is added in one place and each cause has one reading. The module reads the model, never
//! the brand: `scope.rs` makes the proof from the answer.

use archkeel_contract::Rule;

use crate::causes::{Cause, Held, Part};
use crate::dropped_gaps;
use crate::model::Model;
use crate::pair_gaps::reads;
use crate::proof::State;
use crate::reason::Reason;
use crate::receipts::{self, GapScope};
use crate::scope_receipt::{dynamic_import, gap_scope, receipt, rescued, scan_proof};

/// What a scope proof is for: one rule of the contract, or the whole run.
#[derive(Clone, Copy)]
enum Subject<'a> {
    Rule(&'a Rule),
    Run,
}

/// One source of doubt. Each is read for a rule or for the run, or for both.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Source {
    /// The rule is a rule of this contract.
    Foreign,
    /// The receipt of an `interface_boundary` rule comes first: it states its own cause.
    InterfaceReceipt,
    /// The scope state that the model made one time: a fact that makes it incomplete, or a part
    /// that the core cannot read.
    State,
    /// A profile limit holds the subject when it reads the part that the limit names.
    ProfileLimit,
    /// A gap that states its effect holds the subject when it reads the effect.
    ScopedGaps,
    /// A kept pair gap holds only what it can change; a gap that the drop rule drops holds a rule
    /// as well when it can change it.
    PairGaps,
    /// The gaps that the drop rule drops, read for the whole run.
    DroppedGaps,
    /// A dynamic import that reaches the rule.
    DynamicImport,
    /// The receipt of the rule: it selects a module of the reply.
    Receipt,
}

/// The sources of a rule, in the order that the proof reads them. A fact that makes the scope
/// incomplete comes before a part that the core cannot read; the doubt sources of the rule come
/// before its receipt, so each kind states them.
const RULE_ORDER: [Source; 8] = [
    Source::Foreign,
    Source::InterfaceReceipt,
    Source::State,
    Source::ProfileLimit,
    Source::ScopedGaps,
    Source::PairGaps,
    Source::DynamicImport,
    Source::Receipt,
];

/// The sources of the whole run, in the order that the proof reads them.
const RUN_ORDER: [Source; 5] = [
    Source::State,
    Source::ProfileLimit,
    Source::PairGaps,
    Source::ScopedGaps,
    Source::DroppedGaps,
];

/// What a source leaves for the end of the proof.
#[derive(Default)]
struct Carry<'id> {
    /// A part that the core cannot read: it ends the proof after every cause was read.
    unread: Option<Part>,
    /// The part that a profile limit names, for the whole run.
    limited: Option<Part>,
    /// The gap scope of a rule, spent when the proof is made.
    gaps: Option<GapScope<'id>>,
}

/// The sources of a subject, in order.
fn order(subject: Subject<'_>) -> &'static [Source] {
    match subject {
        Subject::Rule(_) => &RULE_ORDER,
        Subject::Run => &RUN_ORDER,
    }
}

/// Read the sources of `subject` in order. The first that holds is the cause.
fn read_all<'id>(model: &Model, subject: Subject<'_>) -> Result<Carry<'id>, Reason> {
    let mut carry = Carry::default();
    for source in order(subject) {
        read(model, *source, subject, &mut carry)?;
    }
    Ok(carry)
}

/// `Ok` when the model saw the whole scope of `rule`: no source holds and no part is unread.
pub(crate) fn rule(model: &Model, rule: &Rule) -> Result<(), Reason> {
    let mut carry = read_all(model, Subject::Rule(rule))?;
    if let Some(gaps) = carry.gaps.take() {
        gaps.spent();
    }
    carry.unread.map_or(Ok(()), |part| Err(part.into()))
}

/// Every source that holds `rule`, in the order of `RULE_ORDER`, then the part that the core cannot read. The
/// first one is the reason of the rule (`rule`). The others are causes that the rule has as well: a baseline
/// keys them all, so the key of a rule does not move when the first cause is resolved and the next one is
/// shown (AD-1290). Empty when `rule` returns `Ok`.
pub(crate) fn rule_causes(model: &Model, rule: &Rule) -> Vec<Reason> {
    let subject = Subject::Rule(rule);
    let mut carry = Carry::default();
    let mut found: Vec<Reason> = Vec::new();
    for source in order(subject) {
        if let Err(reason) = read(model, *source, subject, &mut carry) {
            found.push(reason);
        }
    }
    if let Some(gaps) = carry.gaps.take() {
        gaps.spent();
    }
    found.extend(carry.unread.map(Reason::from));
    found
}

/// `Ok` when the model saw the whole scope of the run: no source holds and no part is unread.
pub(crate) fn run(model: &Model) -> Result<(), Reason> {
    let carry = read_all(model, Subject::Run)?;
    match model.scope_state() {
        State::Unread(part) => Err(part.clone().into()),
        _ => carry.limited.map_or(Ok(()), |part| Err(part.into())),
    }
}

/// Read one source for a subject. The match lists every source and has no catch-all arm.
fn read<'id>(
    model: &Model,
    source: Source,
    subject: Subject<'_>,
    carry: &mut Carry<'id>,
) -> Result<(), Reason> {
    match source {
        Source::Foreign => foreign(model, subject),
        Source::InterfaceReceipt => interface_receipt(model, subject),
        Source::State => state(model, subject, carry),
        Source::ProfileLimit => profile_limit(model, subject, carry),
        Source::ScopedGaps => scoped_gaps(model, subject),
        Source::PairGaps => pair_gaps(model, subject, carry),
        Source::DroppedGaps => dropped(model, subject),
        Source::DynamicImport => dynamic(model, subject),
        Source::Receipt => rule_receipt(model, subject),
    }
}

fn foreign(model: &Model, subject: Subject<'_>) -> Result<(), Reason> {
    match subject {
        Subject::Rule(rule) if !model.contract().rules().contains(rule) => {
            Err(Part::ForeignRule.into())
        }
        Subject::Rule(_) | Subject::Run => Ok(()),
    }
}

fn interface_receipt(model: &Model, subject: Subject<'_>) -> Result<(), Reason> {
    match subject {
        Subject::Rule(Rule::InterfaceBoundary(rule)) => crate::interface::receipt(model, rule),
        Subject::Rule(_) | Subject::Run => Ok(()),
    }
}

fn state<'id>(model: &Model, subject: Subject<'_>, carry: &mut Carry<'id>) -> Result<(), Reason> {
    match (subject, model.scope_state()) {
        (Subject::Rule(rule), State::Incomplete(reason)) => Err(rescued(model, rule, reason)),
        (Subject::Rule(_), State::Unread(part)) => {
            carry.unread = Some(part.clone());
            Ok(())
        }
        (Subject::Run, State::Incomplete(reason)) => Err(reason.clone()),
        (Subject::Rule(_), State::Complete)
        | (Subject::Run, State::Unread(_) | State::Complete) => Ok(()),
    }
}

// AD-500, AD-644: a profile limit holds the subject when it reads the part that it limits.
fn profile_limit<'id>(
    model: &Model,
    subject: Subject<'_>,
    carry: &mut Carry<'id>,
) -> Result<(), Reason> {
    match subject {
        Subject::Rule(rule) => {
            crate::proof::hold_rule(model.contract(), model.graph(), rule, &mut carry.unread)
        }
        Subject::Run => {
            carry.limited = crate::proof::hold_run(model.contract(), model.graph())?;
            Ok(())
        }
    }
}

// AD-564: a gap that states its effect holds the subject when it reads the effect.
fn scoped_gaps(model: &Model, subject: Subject<'_>) -> Result<(), Reason> {
    let found = match subject {
        Subject::Rule(rule) => crate::gap_effects::held(model, rule),
        Subject::Run => crate::gap_effects::every(model),
    };
    found.map_or(Ok(()), |scoped| {
        Err(Reason::NotComplete(Cause::ScopedGaps(scoped)))
    })
}

// Slice S7 (AD-384), AD-418: a rule reads the gap scope of its own reading (kept gaps, then the
// dropped gaps that can change it); the run reads each kept gap.
fn pair_gaps<'id>(
    model: &Model,
    subject: Subject<'_>,
    carry: &mut Carry<'id>,
) -> Result<(), Reason> {
    match subject {
        Subject::Rule(rule) => {
            carry.gaps =
                Some(gap_scope(model, rule).map_err(|reason| rescued(model, rule, &reason))?);
            Ok(())
        }
        Subject::Run => {
            let kept = model
                .pairs()
                .kept
                .iter()
                .map(|gap| (gap.source.as_str(), gap.target.as_str()));
            holds(kept, Cause::PairGaps)
        }
    }
}

/// The pair gaps that hold, as the cause that `cause` makes of them; `Ok` for no gap.
fn holds<'a>(
    gaps: impl Iterator<Item = (&'a str, &'a str)>,
    cause: fn(Held) -> Cause,
) -> Result<(), Reason> {
    Held::of(gaps).map_or(Ok(()), |held| Err(Reason::NotComplete(cause(held))))
}

// The gaps that the drop rule drops hold the run when they can change a rule of the contract; a
// rule reads them in `pair_gaps`.
fn dropped(model: &Model, subject: Subject<'_>) -> Result<(), Reason> {
    match subject {
        Subject::Rule(_) => Ok(()),
        Subject::Run => {
            let rules = model.contract().rules();
            let components = model.contract().components();
            let dropped = model.pairs().dropped.iter().filter(|gap| {
                rules
                    .iter()
                    .any(|rule| dropped_gaps::holds(gap, rule, &reads(rule, components, rules)))
            });
            holds(
                dropped.map(|gap| (gap.source.as_str(), gap.target.as_str())),
                Cause::AllowedPairGaps,
            )
        }
    }
}

fn dynamic(model: &Model, subject: Subject<'_>) -> Result<(), Reason> {
    match subject {
        Subject::Rule(rule) if dynamic_import(model, rule) => {
            Err(Reason::NotComplete(Cause::DynamicImport))
        }
        Subject::Rule(_) | Subject::Run => Ok(()),
    }
}

fn rule_receipt(model: &Model, subject: Subject<'_>) -> Result<(), Reason> {
    let Subject::Rule(rule) = subject else {
        return Ok(());
    };
    match rule {
        Rule::NoComponentCycles(cycle) => receipts::cycle(model, cycle, scan_proof(model))?,
        Rule::InterfaceBoundary(_) => receipts::interface(model, scan_proof(model))?,
        Rule::CompleteRequires(_) => {
            receipt(model, rule)?;
            receipts::requires(model, scan_proof(model))?;
        }
        _ => receipt(model, rule)?,
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A source is read once for a subject, and a rule and a run share the sources that they both
    /// read: `State`, `ProfileLimit`, `ScopedGaps` and `PairGaps`.
    #[test]
    fn each_order_reads_a_source_once_and_both_read_the_shared_ones() {
        for order in [&RULE_ORDER[..], &RUN_ORDER[..]] {
            for (at, source) in order.iter().enumerate() {
                assert!(
                    !order[at + 1..].contains(source),
                    "{source:?} is read twice"
                );
            }
        }
        for shared in [
            Source::State,
            Source::ProfileLimit,
            Source::ScopedGaps,
            Source::PairGaps,
        ] {
            assert!(
                RULE_ORDER.contains(&shared) && RUN_ORDER.contains(&shared),
                "{shared:?}"
            );
        }
    }

    /// The run reads a kept pair gap before a gap that states its effect; a rule reads the effect
    /// first, as before the one list. A fact that makes the scope incomplete comes first for both.
    #[test]
    fn the_orders_keep_the_readings_of_each_subject() {
        let at = |order: &[Source], source| order.iter().position(|s| *s == source).unwrap();
        assert!(at(&RUN_ORDER, Source::PairGaps) < at(&RUN_ORDER, Source::ScopedGaps));
        assert!(at(&RULE_ORDER, Source::ScopedGaps) < at(&RULE_ORDER, Source::PairGaps));
        assert_eq!(RUN_ORDER[0], Source::State);
        assert!(at(&RULE_ORDER, Source::State) < at(&RULE_ORDER, Source::ProfileLimit));
        assert!(at(&RULE_ORDER, Source::DynamicImport) < at(&RULE_ORDER, Source::Receipt));
    }
}
