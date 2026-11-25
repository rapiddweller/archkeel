// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reach model of the compiler type-reach facts (AD-1047, stage 2, shadow mode).
//!
//! `Facts` unions the files of one configuration. `Reach` decides, for a pair of scan modules `(a, b)`
//! that a gap holds, whether no body of `a` can hold the self type of any impl in `b` that runs code.
//! Nothing in a scan reads it: it only measures what a later stage may drop.
//!
//! The type reach of `a` is the ADTs that its bodies mention, the instances of its generic functions,
//! the hidden types of its opaque types and coroutines, the fields of those ADTs and the associated
//! types of the impls they have. For each `dyn` trait in reach it adds each type that is coerced to it:
//! by a body, from a type parameter (hole H1), by code outside the workspace that a type reaches
//! (hole H2), or by upcasting from a sub-trait.

use crate::type_reach_facts::{ImplFacts, Names};
use crate::type_reach_fold::Reach;
use std::collections::{BTreeMap, BTreeSet};

/// How a `dyn` trait in reach is read.
pub enum Mode {
    /// Every type that any module mentions: the loosest reading, for a report.
    Loose,
    /// Each type that a body coerces to the trait (run-time reachable): a measurement. It is unsound for
    /// code that no workspace body calls, and for callers outside the scan.
    Rta,
    /// Each type that implements the trait, and each type that a body coerces to it: what a `dyn` call can
    /// reach whatever the callers (class hierarchy). The filter reads this.
    Cha,
}

/// What the model says of one pair `(a, b)`: no body of `a` can hold the self type of an impl in `b`.
pub enum Verdict {
    /// Excluded in every configuration.
    Excluded,
    /// Kept, with the first cause.
    Kept(Cause),
}

/// Why a pair stays.
pub enum Cause {
    /// A configuration has no facts for `a` (unbuilt, cfg-only, a build script).
    NoFacts,
    /// `b` has no impl that runs code in the facts.
    NoImpl,
    /// An impl of `b` has a self type without an ADT (blanket, primitive): it can run for any type.
    NonAdtSelf,
    /// A self type of an impl of `b` is in the type reach of `a`.
    Reached,
}

impl<'f> Reach<'f> {
    /// The ADTs that a body of the scan module `a` can hold; `None` when `a` has no facts. `mode` says how a `dyn`
    /// trait in reach adds types.
    pub fn reach_of(&self, a: &str, mode: &Mode) -> Option<Names> {
        let f = self.facts;
        let (own, functions, _) = self.parts.get(a)?;
        if own.is_empty() {
            return None;
        }
        let (mut types, mut dyns, mut opaques) = (Names::new(), Names::new(), Names::new());
        for m in own {
            types.extend(f.mods[m].adts.iter().cloned());
            dyns.extend(f.mods[m].dyns.iter().cloned());
            opaques.extend(f.mods[m].opaques.iter().cloned());
        }
        for id in functions {
            let (adts, instance_dyns) = self.inst.get(id).cloned().unwrap_or_default();
            types.extend(adts);
            dyns.extend(instance_dyns);
        }
        let mut impls_of: BTreeMap<&str, Vec<&ImplFacts>> = BTreeMap::new();
        for imp in f
            .impls
            .iter()
            .filter(|i| i.tr.is_some() && !(i.assoc.is_empty() && i.assoc_dyns.is_empty()))
        {
            imp.adts
                .iter()
                .for_each(|x| impls_of.entry(x.as_str()).or_default().push(imp));
        }
        // A blanket impl has no ADT in its self type, so `impls_of` misses it: it applies to any type, and its
        // associated types are reached whenever the module reaches a type (hole H3).
        let blanket: Vec<&ImplFacts> = f
            .impls
            .iter()
            .filter(|i| {
                i.tr.is_some()
                    && i.adts.is_empty()
                    && !(i.assoc.is_empty() && i.assoc_dyns.is_empty())
            })
            .collect();
        let none = Names::new();
        // A `dyn` in a field of a foreign ADT holds what some body coerced to it: workspace code, or code
        // that a type of the workspace reached (`coerced`); not each implementer in the workspace.
        let mut held = Names::new();
        let (mut seen_types, mut seen_dyns, mut seen_opaques, mut seen_held) = (0, 0, 0, 0);
        let mut stale = true;
        while stale {
            let mut more = Names::new();
            for o in opaques.clone() {
                let hidden = f.hidden.get(&o).map(|h| (&h.adts, &h.dyns, &h.opaques));
                let (adts, hidden_dyns, nested) = hidden.unwrap_or((&none, &none, &none));
                more.extend(adts.iter().cloned());
                dyns.extend(hidden_dyns.iter().cloned());
                opaques.extend(nested.iter().cloned());
            }
            for t in &types {
                let adt = f
                    .adts
                    .get(t)
                    .map(|(fields, field_dyns)| (fields, field_dyns));
                let (fields, field_dyns) = adt.unwrap_or((&none, &none));
                more.extend(fields.iter().cloned());
                dyns.extend(field_dyns.iter().cloned());
                // An associated type of a reached impl is reached (hole H3).
                let impls = impls_of
                    .get(t.as_str())
                    .into_iter()
                    .flatten()
                    .chain(&blanket);
                let (assoc, assoc_dyns): (Vec<_>, Vec<_>) =
                    impls.map(|imp| (&imp.assoc, &imp.assoc_dyns)).unzip();
                more.extend(assoc.into_iter().flatten().cloned());
                dyns.extend(assoc_dyns.into_iter().flatten().cloned());
            }
            // An opaque type or a coroutine in a type argument flows by its name (AD-1047).
            opaques.extend(types.iter().filter(|t| f.hidden.contains_key(*t)).cloned());
            for t in &types {
                held.extend(f.foreign_dyn.get(t).into_iter().flatten().cloned());
            }
            for d in dyns.clone() {
                more.extend(self.coerced_to(&d, mode));
                opaques.extend(self.coerced_opaque.get(&d).cloned().unwrap_or_default());
            }
            // A pointer to `()` hides the type of its value: the module reaches what a cast hid, and what
            // calls outside the workspace took with the erasing type in their signature.
            let mut keys: Vec<&str> = types
                .iter()
                .filter(|t| f.erased.1.contains(*t) || f.via.contains_key(*t))
                .map(String::as_str)
                .collect();
            if own.iter().any(|m| f.erased.0.contains(m)) {
                keys.push("<ptr>");
            }
            if !keys.is_empty() {
                more.extend(f.lost.0.iter().cloned());
                dyns.extend(f.lost.1.iter().cloned());
            }
            for key in keys {
                let (adts, via_dyns) = f.via.get(key).cloned().unwrap_or_default();
                more.extend(adts);
                dyns.extend(via_dyns);
            }
            for d in &held {
                more.extend(self.coerced.get(d).cloned().unwrap_or_default());
            }
            types.extend(more);
            let now = (types.len(), dyns.len(), opaques.len(), held.len());
            stale = now != (seen_types, seen_dyns, seen_opaques, seen_held);
            (seen_types, seen_dyns, seen_opaques, seen_held) = now;
        }
        Some(types)
    }

    /// The types that a `dyn` trait in reach can hold: what is coerced to it, or in the loose reading every type.
    fn coerced_to(&self, tr: &str, mode: &Mode) -> Names {
        let mut found = self.coerced.get(tr).cloned().unwrap_or_default();
        match mode {
            Mode::Rta => {}
            Mode::Loose => found.extend(self.anywhere.iter().cloned()),
            Mode::Cha => {
                let (types, blanket) = self.implemented.get(tr).cloned().unwrap_or_default();
                found.extend(types);
                if blanket {
                    found.extend(self.anywhere.iter().cloned());
                }
            }
        }
        found
    }

    /// How many scan modules have facts in this configuration.
    pub fn matched(&self, known: &BTreeSet<String>) -> usize {
        self.parts
            .keys()
            .filter(|name| known.contains(*name))
            .count()
    }

    /// The verdict of one configuration for the pair `(a, b)`. `cache` keeps the reach of each module.
    pub fn decide(
        &self,
        (a, b): (&str, &str),
        mode: &Mode,
        cache: &mut BTreeMap<String, Option<Names>>,
    ) -> Verdict {
        let Some(reach) = cache
            .entry(a.to_string())
            .or_insert_with(|| self.reach_of(a, mode))
            .clone()
        else {
            return Verdict::Kept(Cause::NoFacts);
        };
        let at = self
            .parts
            .get(b)
            .map(|p| p.2.as_slice())
            .unwrap_or_default();
        let pool: Vec<&ImplFacts> = at.iter().map(|i| &self.facts.impls[*i]).collect();
        if pool.is_empty() {
            return Verdict::Kept(Cause::NoImpl);
        }
        if pool.iter().any(|i| i.adts.is_empty()) {
            return Verdict::Kept(Cause::NonAdtSelf);
        }
        if pool
            .iter()
            .any(|i| i.adts.iter().any(|x| reach.contains(x)))
        {
            return Verdict::Kept(Cause::Reached);
        }
        Verdict::Excluded
    }
}

#[cfg(test)]
#[path = "type_reach_model_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "type_reach_close_tests.rs"]
mod close_tests;
