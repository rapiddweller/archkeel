// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The filter of a scan over the type reach (AD-1047).

// Consumer: the trait-impl, destructor and receiver gaps of `impl_flow` (AD-1047).

use crate::site::Site;
use crate::type_reach_facts::{Facts, Names, SelectedFacts};
use crate::type_reach_fold::Reach;
use crate::type_reach_model::{Mode, Verdict};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};

/// The filter of a scan: a pair is excluded only when every configuration excludes it (class hierarchy `dyn`,
/// all impls of the target). A pair without facts for its source stays. It reads facts only, never
/// the gaps, so the order of the candidates cannot change an answer.
pub struct Filter<'f> {
    models: Vec<Reach<'f>>,
    reaches: RefCell<Vec<BTreeMap<String, Option<Names>>>>,
    memo: RefCell<BTreeMap<(String, String), bool>>,
    matched: usize,
}

impl<'f> Filter<'f> {
    /// The reason of the scan-wide gap when the facts name no module of the scan.
    pub fn no_module() -> &'static str {
        "The compiler type-reach facts name no module of this scan: the namespace or the crate names differ. Each trait-impl, destructor and receiver gap stays (AD-1047)."
    }
    /// One model for each configuration; `known` names the modules of the scan.
    pub fn new(facts: &'f [Facts], known: &BTreeSet<String>) -> Filter<'f> {
        let models: Vec<Reach<'f>> = facts.iter().map(|f| Reach::new(f, known)).collect();
        let reaches = RefCell::new(models.iter().map(|_| BTreeMap::new()).collect());
        let matched = models.iter().map(|m| m.matched(known)).sum();
        Filter {
            models,
            reaches,
            memo: RefCell::new(BTreeMap::new()),
            matched,
        }
    }

    /// How many modules of the scan the facts name, over all configurations. Zero means that the facts
    /// are of another scan (another namespace or crate names): no pair can be decided.
    pub fn matched(&self) -> usize {
        self.matched
    }

    /// The calls of `PartialEq::eq` that the compiler resolved to an impl in another scan module, in every
    /// configuration of the matrix. Two edges that a rule combines (a cycle) must come from one configuration,
    /// and an edge does not say which. A site that one configuration lacks stays a gap (AD-1136).
    pub(crate) fn selected(&self) -> Vec<&SelectedFacts> {
        let key = |s: &SelectedFacts| {
            (
                s.from.clone(),
                s.to.clone(),
                s.imp.clone(),
                s.file.clone(),
                s.impl_file.clone(),
                s.line,
                s.column,
            )
        };
        let Some((first, rest)) = self.models.split_first() else {
            return Vec::new();
        };
        let others: Vec<BTreeSet<_>> = rest
            .iter()
            .map(|m| m.selected.iter().map(key).collect())
            .collect();
        let mut seen = BTreeSet::new();
        let kept = first
            .selected
            .iter()
            .filter(|s| others.iter().all(|set| set.contains(&key(s))));
        kept.filter(|s| seen.insert(key(s))).collect()
    }

    /// The scan module that the call `x.m()` at a place reaches, or `None` for a call that some configuration does
    /// not resolve to one callee. The inner `None` is a callee outside the workspace. Every configuration must
    /// hold the place with one and the same callee: a feature can change a call (AD-1185).
    fn callee(&self, file: &str, line: i64, column: i64) -> Option<Option<&str>> {
        let key = (file.to_owned(), line, column);
        let mut found = self.models.iter().map(|m| m.callees.get(&key));
        let first = found.next()??;
        let mut one = first.iter();
        let (callee, rest) = (one.next()?, one.next());
        let same = found.all(|set| set.is_some_and(|s| s.len() == 1 && s.contains(callee)));
        (rest.is_none() && same).then_some(callee.as_deref())
    }

    /// True when a candidate `(a, b)` at a place falls: the facts exclude the pair, or the compiler resolved the
    /// method call at the place to another module than `b`. An execution candidate has no written call (AD-1185).
    pub(crate) fn drops(
        reach: Option<&Filter<'_>>,
        [a, b, file]: [&str; 3],
        site: &Site,
        execution: bool,
    ) -> bool {
        let Some(this) = reach else {
            return false;
        };
        let elsewhere = || {
            this.callee(file, site.line, site.column)
                .is_some_and(|c| c != Some(b))
        };
        this.excluded(a, b) || (!execution && elsewhere())
    }

    /// True when no body of `a` can hold the self type of an impl of `b` that runs code.
    pub fn excluded(&self, a: &str, b: &str) -> bool {
        let key = (a.to_string(), b.to_string());
        if let Some(known) = self.memo.borrow().get(&key) {
            return *known;
        }
        let mut caches = self.reaches.borrow_mut();
        let each = self.models.iter().zip(caches.iter_mut());
        let all = each
            .map(|(m, cache)| m.decide((a, b), &Mode::Cha, cache))
            .all(|v| matches!(v, Verdict::Excluded));
        let excluded = all && !self.models.is_empty();
        self.memo.borrow_mut().insert(key, excluded);
        excluded
    }
}
