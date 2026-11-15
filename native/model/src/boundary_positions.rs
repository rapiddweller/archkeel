// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The positions of a `boundary_types` rule (AD-550): the public entries of each component, the
//! callables that they reach, the written type of each parameter and return, and one verdict for
//! each position.
//!
//! The model names no language. A position is one parameter or the return of a function or a
//! method that a `public` entry covers, below the `source` of the rule. It is allowed, a violation
//! or a named gap. The reading never guesses what it cannot read: an entry with no record, a class
//! with a base of the repository, a member that has no record and a signature with no shape are
//! each a gap row, so a PASS needs a complete surface.

use std::collections::HashSet;

use archkeel_contract::{BoundaryAllowance, BoundaryTypes, RuleKind};
use archkeel_facts::type_shape::TypeShape;
use archkeel_facts::vocab::MethodKind;

use crate::boundary_facts::{Callable, Class, Entry, Origin};
use crate::boundary_judge::{judge, GapCause, Leaf, Surface};
use crate::boundary_surface::{declared, entries, names, PublicEntry};
use crate::model::Model;
use crate::reason::{Hygiene, Reason, Unsupported};

/// One position that breaks the rule and has no exact exception.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Position {
    /// `<facade name>:<position>`.
    pub subject: String,
    pub qualified_name: String,
    /// The parameter name as the record writes it, or `return`.
    pub position: String,
    /// The written type.
    pub text: String,
    pub leaves: Vec<Leaf>,
    pub evidence: Vec<String>,
}

/// One named gap: a position or an entry that syntax does not decide.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GapRow {
    pub subject: String,
    pub cause: GapCause,
    pub text: String,
}

impl GapRow {
    /// The reason of the row: the cause and the written text.
    pub fn reason(&self) -> String {
        format!("{}: {}", self.cause.as_str(), self.text)
    }
}

/// An exception of the contract that matches no position of the surface.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Stale {
    pub subject: String,
    pub annotation: String,
}

/// What the rule reads from one run.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Reading {
    /// The number of positions that the rule read.
    pub positions: usize,
    pub violations: Vec<Position>,
    pub gaps: Vec<GapRow>,
    pub stale: Vec<Stale>,
}

/// True for the name of a method that is part of an interface (`is_public_method_name`).
fn method_name(name: &str) -> bool {
    !name.starts_with('_') || (name.starts_with("__") && name.ends_with("__"))
}

/// The reading of one rule, or the reason that the reply has no shapes to read.
pub fn read(model: &Model, rule: &BoundaryTypes) -> Result<Reading, Reason> {
    let graph = model.graph();
    let Some(facts) = graph.boundary() else {
        let kind = RuleKind::BoundaryTypes;
        return Err(Reason::Unsupported(Unsupported::Rule(kind)));
    };
    let scanned: HashSet<&str> = graph.modules().iter().map(|(_, m)| m.name()).collect();
    let declared = declared(model, facts);
    let mut reader = Reader {
        surface: Surface {
            facts,
            declared: &declared,
            scanned: &scanned,
        },
        allowances: rule.allowed_positions(),
        used: vec![false; rule.allowed_positions().len()],
        seen: HashSet::new(),
        reading: Reading::default(),
    };
    // A definition that two facades reach is named by the first: the sorted facade and name.
    let mut covered = entries(model, Some(rule));
    covered.sort_by(|a, b| (&a.module, &a.name).cmp(&(&b.module, &b.name)));
    for entry in covered {
        reader.entry(model, &entry);
    }
    reader.finish();
    Ok(reader.reading)
}

/// The receipt of the rule: it selects a module, it reads a position, and its surface has no named
/// gap. A gap holds back a PASS and decides nothing.
pub(crate) fn receipt(model: &Model, rule: &BoundaryTypes) -> Result<(), Reason> {
    if model.source_modules(rule.source().as_text()).is_empty() {
        return Err(Reason::NoSubjects);
    }
    let reading = read(model, rule)?;
    let Some(first) = reading.gaps.first() else {
        // A rule that reads no position proves nothing: the surface may be a typo of the contract.
        return if reading.positions == 0 {
            Err(Reason::NoSubjects)
        } else {
            Ok(())
        };
    };
    let detail = format!(
        "{} positions or entries of the public surface are named gaps; the first is {} ({})",
        reading.gaps.len(),
        first.subject,
        first.reason()
    );
    Err(Reason::Hygiene(Hygiene::new(
        "boundary_type_position",
        detail,
    )))
}

struct Reader<'a> {
    surface: Surface<'a>,
    allowances: &'a [BoundaryAllowance],
    used: Vec<bool>,
    seen: HashSet<String>,
    reading: Reading,
}

impl Reader<'_> {
    fn gap(&mut self, subject: String, cause: GapCause, text: &str) {
        self.reading.gaps.push(GapRow {
            subject,
            cause,
            text: text.to_owned(),
        });
    }

    fn entry(&mut self, model: &Model, entry: &PublicEntry) {
        match names(model, entry) {
            Ok(covered) => covered.iter().for_each(|name| self.name(entry, name)),
            Err(gap) => self.reading.gaps.push(gap),
        }
    }

    /// One covered name: the rule names a position by the name that the facade gives
    /// (`facade_module.name`), as the exceptions of a contract do, not by the defining module.
    fn name(&mut self, entry: &PublicEntry, name: &str) {
        let facade = format!("{}.{name}", entry.module);
        if self.surface.scanned.contains(facade.as_str()) {
            return;
        }
        let facts = self.surface.facts;
        match facts.origin(&entry.module, name) {
            Origin::Defined(qualified, Entry::Callable(callable)) => {
                self.callable(qualified, &facade, callable);
            }
            Origin::Defined(qualified, Entry::Class(class)) => {
                self.class(qualified, &facade, class)
            }
            Origin::Defined(_, Entry::Value) | Origin::Module => {}
            Origin::Missing(last) => self.missing(entry, name, &last),
        }
    }

    /// A covered name whose definition has no record.
    fn missing(&mut self, entry: &PublicEntry, name: &str, last: &str) {
        let subject = format!("{}:{name}", entry.module);
        if !self.surface.scanned.contains(last) {
            let text = "a name of a module outside the scan";
            return self.gap(subject, GapCause::ExternalType, text);
        }
        if entry.name.is_some() {
            return self.gap(
                subject,
                GapCause::UnresolvedFacadeEntry,
                "no record for the entry",
            );
        }
        let text = "no record: a decorated, conditional or unread definition";
        self.gap(subject, GapCause::NoRecord, text);
    }

    fn class(&mut self, qualified: &str, facade: &str, class: &Class) {
        if !self.seen.insert(qualified.to_owned()) {
            return;
        }
        // A base that has a record is a class of the repository: its members are inherited and
        // the reading does not follow them. A base without a record is outside the scan.
        let facts = self.surface.facts;
        if let Some(base) = class.bases.iter().find(|base| facts.entry(base).is_some()) {
            self.gap(facade.to_owned(), GapCause::InheritedSurface, base);
        }
        self.members(qualified, facade, class);
        let callables = class
            .methods
            .iter()
            .filter_map(|method| match facts.entry(method) {
                Some(Entry::Callable(callable)) if method_name(&callable.name) => {
                    Some((method, callable))
                }
                _ => None,
            });
        for (method, callable) in callables {
            let named = format!("{facade}.{}", callable.name);
            self.callable(method, &named, callable);
        }
    }

    /// Each member that the class body binds has a record, an attribute declaration or a nested
    /// class; a class with its members withheld is one gap.
    fn members(&mut self, qualified: &str, facade: &str, class: &Class) {
        let Some(members) = &class.members else {
            let text = "the members of the class are withheld";
            return self.gap(facade.to_owned(), GapCause::MemberNoRecord, text);
        };
        for member in members.iter().filter(|member| method_name(member)) {
            let own = format!("{qualified}.{member}");
            let known = class.methods.contains(&own)
                || class.attributes.contains(member)
                || self.surface.facts.entry(&own).is_some();
            if !known {
                let named = format!("{facade}.{member}");
                self.gap(named, GapCause::MemberNoRecord, "a member with no record");
            }
        }
    }

    fn callable(&mut self, qualified: &str, facade: &str, callable: &Callable) {
        if !self.seen.insert(qualified.to_owned()) {
            return;
        }
        let Some(returns) = &callable.returns else {
            let text = "the collector wrote no shape for this signature";
            return self.gap(facade.to_owned(), GapCause::ShapesNotWritten, text);
        };
        let receiver = callable
            .method
            .is_some_and(|kind| kind != MethodKind::Static)
            && callable
                .slots
                .first()
                .is_some_and(|slot| matches!(slot.kind.as_str(), "positional" | "positional_only"));
        for slot in callable.slots.iter().skip(usize::from(receiver)) {
            self.slot(facade, &slot.name, slot.shape.as_ref(), callable);
        }
        // A constructor has no return position.
        if callable.method != Some(MethodKind::Constructor) {
            self.slot(facade, "return", Some(returns), callable);
        }
    }

    fn slot(&mut self, facade: &str, position: &str, shape: Option<&TypeShape>, owner: &Callable) {
        match shape {
            Some(shape) => self.position(facade, position, shape, owner),
            None => self.gap(
                format!("{facade}:{position}"),
                GapCause::ShapesNotWritten,
                "the collector wrote no shape for this parameter",
            ),
        }
    }

    fn position(&mut self, facade: &str, position: &str, shape: &TypeShape, owner: &Callable) {
        self.reading.positions += 1;
        let subject = format!("{facade}:{position}");
        let text = shape.text().to_owned();
        let judged = judge(shape, &self.surface, 0);
        let (mut broad, other): (Vec<Leaf>, Vec<Leaf>) =
            judged.leaves.into_iter().partition(|leaf| leaf.broad);
        let unread = self.exceptions(facade, position, &text, &mut broad);
        let mut gaps = judged.gaps;
        if unread && !broad.is_empty() {
            // The exception names a depth, a field, an alias or a mapping that syntax does not read.
            gaps.push((GapCause::AllowanceNotRead, text.clone()));
            broad.clear();
        }
        let leaves: Vec<Leaf> = broad.into_iter().chain(other).collect();
        if !leaves.is_empty() {
            self.reading.violations.push(Position {
                subject,
                qualified_name: facade.to_owned(),
                position: position.to_owned(),
                text,
                leaves,
                evidence: owner.evidence.clone(),
            });
        } else if let Some((cause, written)) = gaps.into_iter().min() {
            self.gap(subject, cause, &written);
        }
    }

    /// Apply the exceptions of the contract that name this position and its exact text: a plain one
    /// allows the one broad leaf that is the position itself. True when an exception names more
    /// (a depth, a field, an alias, a mapping) than syntax reads.
    fn exceptions(
        &mut self,
        facade: &str,
        position: &str,
        text: &str,
        broad: &mut Vec<Leaf>,
    ) -> bool {
        let mut unread = false;
        for (index, item) in self.allowances.iter().enumerate() {
            let same = item.qualified_name() == facade
                && item.position() == position
                && item.annotation() == text;
            if !same {
                continue;
            }
            self.used[index] = true;
            if !exact(item) {
                unread = true;
                continue;
            }
            let roots = broad.iter().filter(|leaf| leaf.depth == 0).count();
            if roots == 1 {
                broad.retain(|leaf| leaf.depth != 0);
            }
        }
        unread
    }

    /// An exception that matches no position is stale, when the surface has no gap that could hide
    /// the position.
    fn finish(&mut self) {
        if !self.reading.gaps.is_empty() {
            return;
        }
        for (index, item) in self.allowances.iter().enumerate() {
            if !self.used[index] {
                self.reading.stale.push(Stale {
                    subject: format!("{}:{}", item.qualified_name(), item.position()),
                    annotation: item.annotation().clone(),
                });
            }
        }
    }
}

/// An exception that names only the position and its exact text.
fn exact(item: &BoundaryAllowance) -> bool {
    item.field_path().is_empty()
        && item.container_depth().is_none()
        && item.mapping_depth().is_none()
        && item.alias_body().is_none()
        && item.key_alias_body().is_none()
        && item.literal_mapping_arm().is_none()
        && !item.native_mapping()
}
