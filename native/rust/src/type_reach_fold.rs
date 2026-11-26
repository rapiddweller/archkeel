// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reach model of one configuration, and its folds: the instances of generic functions, and the types
//! that each `dyn` trait holds (AD-1047).

use crate::type_reach_facts::{Facts, Names, Parts, SelectedFacts};
use std::collections::{BTreeMap, BTreeSet};

/// The reach model of one configuration. `known` names the modules that the scan uses: a rustc module
/// belongs to the longest of these that is a prefix of its path (an inline `mod tests` joins its file).
pub struct Reach<'f> {
    pub(crate) facts: &'f Facts,
    /// For each generic function: the ADTs and the `dyn` traits that it can be instantiated with.
    pub(crate) inst: BTreeMap<String, (Names, Names)>,
    pub(crate) coerced: BTreeMap<String, Names>,
    /// For each trait: the ADTs in the self type of its impls, and whether an impl has no ADT (blanket).
    pub(crate) implemented: BTreeMap<String, (Names, bool)>,
    pub(crate) anywhere: Names,
    /// Opaque types (coroutines) that each `dyn` trait can hold: the hidden types of a `dyn Future`.
    pub(crate) coerced_opaque: BTreeMap<String, Names>,
    /// For each scan module: its rustc modules, its generic functions and the indexes of its impls.
    pub(crate) parts: Parts,
    /// The selected impls whose two ends are scan modules, with the scan names (AD-1136).
    pub(crate) selected: Vec<SelectedFacts>,
    /// The scan module that each resolved method call at a place (file, line, column) reaches: `None` for a foreign
    /// callee. Two callees at one place stay both (AD-1185).
    pub(crate) callees: BTreeMap<(String, i64, i64), BTreeSet<Option<String>>>,
}

impl<'f> Reach<'f> {
    /// Fold the instances of the generic functions, the coercions and the impls of one configuration.
    pub fn new(facts: &'f Facts, known: &BTreeSet<String>) -> Reach<'f> {
        // Each scan module is `<namespace>.<crate>.<module>`; the facts name `<crate>::<module>`.
        let namespace = known
            .iter()
            .next()
            .and_then(|name| name.split('.').next())
            .unwrap_or_default();
        let mut owner = BTreeMap::new();
        let paths = facts
            .mods
            .keys()
            .chain(facts.impls.iter().map(|i| &i.module))
            .chain(facts.fns.values().map(|(module, _)| module))
            .chain(facts.selected.iter().flat_map(|s| [&s.from, &s.to]))
            .chain(facts.calls.iter().filter_map(|c| c.to.as_ref()));
        for path in paths {
            let mut name = format!("{namespace}.{}", path.replace("::", "."));
            while !known.contains(&name) && name.contains('.') {
                name.truncate(name.rfind('.').unwrap_or(0));
            }
            let kept = if known.contains(&name) {
                name
            } else {
                format!("{namespace}.{}", path.replace("::", "."))
            };
            owner.insert(path.clone(), kept);
        }
        let anywhere = facts
            .mods
            .values()
            .flat_map(|m| m.adts.iter().cloned())
            .collect();
        let mut parts: Parts = BTreeMap::new();
        for m in facts.mods.keys() {
            parts.entry(owner[m].clone()).or_default().0.push(m.clone());
        }
        for (id, (module, _)) in &facts.fns {
            parts
                .entry(owner[module].clone())
                .or_default()
                .1
                .push(id.clone());
        }
        for (at, imp) in facts.impls.iter().enumerate().filter(|(_, i)| i.run) {
            parts
                .entry(owner[&imp.module].clone())
                .or_default()
                .2
                .push(at);
        }
        let selected = facts
            .selected
            .iter()
            .map(|s| SelectedFacts {
                from: owner[&s.from].clone(),
                to: owner[&s.to].clone(),
                imp: s.imp.clone(),
                file: s.file.clone(),
                impl_file: s.impl_file.clone(),
                line: s.line,
                column: s.column,
            })
            .filter(|s| s.from != s.to && known.contains(&s.from) && known.contains(&s.to))
            .collect();
        let mut callees: BTreeMap<(String, i64, i64), BTreeSet<Option<String>>> = BTreeMap::new();
        for c in &facts.calls {
            let to = c.to.as_ref().map(|t| owner[t].clone());
            callees
                .entry((c.file.clone(), c.line, c.column))
                .or_default()
                .insert(to);
        }
        let mut reach = Reach {
            selected,
            callees,
            facts,
            inst: BTreeMap::new(),
            coerced: BTreeMap::new(),
            implemented: BTreeMap::new(),
            anywhere,
            coerced_opaque: facts.coerce_opaque.clone(),
            parts,
        };
        Reach::fold_instances(&mut reach);
        Reach::fold_coercions(&mut reach);
        reach
    }

    /// `A(f)`: the ADTs that a generic function can be instantiated with, over seeds and call edges.
    /// Calls out of the workspace flow into `<foreign>`: those types can be coerced in code that no body shows.
    pub(crate) fn fold_instances(&mut self) {
        let f = self.facts;
        let mut by_item: BTreeMap<&str, Vec<&String>> = BTreeMap::new();
        for (id, (_, implements)) in &f.fns {
            by_item
                .entry(implements.as_deref().unwrap_or(""))
                .or_default()
                .push(id);
        }
        // (the caller whose instances flow too, the callee, the ADTs and `dyn` traits of the arguments).
        let mut flows: Vec<(Option<&String>, &String, &Names, &Names)> = f
            .seeds
            .iter()
            .map(|(to, (a, d))| (None, to, a, d))
            .collect();
        // An edge without a type parameter in its arguments passes no instance of its caller.
        flows.extend(
            f.edges
                .iter()
                .map(|((from, to), (a, d, param))| (param.then_some(from), to, a, d)),
        );
        let mut changed = true;
        while changed {
            changed = false;
            for (from, to, adts, dyns) in &flows {
                let known = from.filter(|o| f.fns.contains_key(*o));
                let mut add = self.instances_of(known);
                add.0.extend(adts.iter().cloned());
                add.1.extend(dyns.iter().cloned());
                let mut targets: Vec<&String> =
                    by_item.get(to.as_str()).cloned().unwrap_or_default();
                targets.push(to);
                changed |= self.flow(&targets, &add);
            }
        }
    }

    fn instances_of(&self, function: Option<&String>) -> (Names, Names) {
        let known = function.and_then(|f| self.inst.get(f.as_str()));
        known.cloned().unwrap_or_default()
    }

    /// Add `add` to the instances of each target. True when one of them grew.
    fn flow(&mut self, targets: &[&String], add: &(Names, Names)) -> bool {
        let mut grew = false;
        for target in targets {
            let have = self.inst.entry((*target).clone()).or_default();
            let before = have.0.len() + have.1.len();
            have.0.extend(add.0.iter().cloned());
            have.1.extend(add.1.iter().cloned());
            grew |= have.0.len() + have.1.len() != before;
        }
        grew
    }

    /// For each `dyn` trait: every type that a body coerces to it (a type parameter takes the instances of
    /// its function, hole H1), every implementer that reaches a call out of the workspace (hole H2) and,
    /// by upcasting, every type coerced to a sub-trait.
    pub(crate) fn fold_coercions(&mut self) {
        let f = self.facts;
        let escaped = self.expand(self.inst.get("<foreign>").cloned().unwrap_or_default().0);
        for (tr, (src, _, params)) in &f.coerce {
            let mut set = src.clone();
            for func in params {
                set.extend(self.expand(self.inst.get(func).cloned().unwrap_or_default().0));
            }
            self.coerced.insert(tr.clone(), set);
        }
        for imp in f.impls.iter().filter(|i| i.tr.is_some()) {
            let tr = imp.tr.clone().unwrap_or_default();
            let seen = self.implemented.entry(tr.clone()).or_default();
            seen.0.extend(imp.adts.iter().cloned());
            seen.1 |= imp.adts.is_empty();
            let found: Vec<String> = escaped
                .iter()
                .filter(|x| imp.adts.is_empty() || imp.adts.contains(*x))
                .cloned()
                .collect();
            self.coerced.entry(tr).or_default().extend(found);
        }
        // Foreign code can coerce a type that flows into it to an open `dyn` (`Any`, an auto trait), when the
        // type has the traits that the blanket impl needs. A trait that is open without a need is met by any type.
        let free: BTreeSet<&String> = f
            .open
            .iter()
            .filter(|(_, n)| n.is_empty())
            .map(|(t, _)| t)
            .collect();
        for (tr, needs) in &f.open {
            let has = |x: &String, need: &String| {
                free.contains(need)
                    || self
                        .implemented
                        .get(need)
                        .is_some_and(|(types, blanket)| *blanket || types.contains(x))
            };
            let found: Vec<String> = escaped
                .iter()
                .filter(|x| needs.iter().all(|need| has(x, need)))
                .cloned()
                .collect();
            self.coerced.entry(tr.clone()).or_default().extend(found);
        }
        let mut changed = true;
        while changed {
            changed = false;
            // A `dyn Sub` can be upcast to each supertrait in code that no body shows (a dependency).
            changed |= self.upcast();
            for (tr, (_, subs, _)) in &f.coerce {
                let inherited: Names = subs
                    .iter()
                    .flat_map(|s| self.coerced.get(s).cloned().unwrap_or_default())
                    .collect();
                let have = self.coerced.entry(tr.clone()).or_default();
                let before = have.len();
                have.extend(inherited);
                changed |= have.len() != before;
            }
        }
    }

    /// Add the hidden types of each opaque type or coroutine in `names`, to a fixpoint: an instance can
    /// name `impl Tr` or an async block, and code that gets it can coerce what it hides (AD-1047).
    fn expand(&self, mut names: Names) -> Names {
        let mut todo: Vec<String> = names.iter().cloned().collect();
        while let Some(name) = todo.pop() {
            let Some(hidden) = self.facts.hidden.get(&name) else {
                continue;
            };
            let fresh: Vec<String> = hidden
                .adts
                .iter()
                .chain(&hidden.opaques)
                .filter(|more| names.insert((*more).clone()))
                .cloned()
                .collect();
            todo.extend(fresh);
        }
        names
    }

    /// Each `dyn Sub` value can be an upcast `dyn Super`: the supers take what the sub-traits hold.
    fn upcast(&mut self) -> bool {
        let pairs: Vec<(&String, &String)> = self
            .facts
            .supers
            .iter()
            .flat_map(|(sub, sups)| sups.iter().map(move |sup| (sup, sub)))
            .collect();
        pairs
            .into_iter()
            .fold(false, |grew, (sup, sub)| self.inherit(sup, sub) | grew)
    }

    /// The types and opaque types of `from` are also those of `to`. True when `to` grew.
    fn inherit(&mut self, to: &str, from: &str) -> bool {
        let types = self.coerced.get(from).cloned().unwrap_or_default();
        let opaques = self.coerced_opaque.get(from).cloned().unwrap_or_default();
        let have = self.coerced.entry(to.to_string()).or_default();
        let before = have.len();
        have.extend(types);
        let more = self.coerced_opaque.entry(to.to_string()).or_default();
        let before_opaque = more.len();
        more.extend(opaques);
        have.len() != before || more.len() != before_opaque
    }
}
