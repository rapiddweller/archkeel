// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `unused_public`: the public items of the modules and the users of each one (AD-670).
//!
//! An item is a module-level symbol that the collector states as declared public. Another
//! component uses it when one of its imports names the item: by the item's own name in its
//! module, or by a route hop of that name (AD-604). The binary or another target of the same
//! package counts too (AD-622). The model counts only a use that the facts prove.
//!
//! An item with no proven user is a violation, except when a use may exist that the facts do not
//! show; then it is undecided:
//! - a glob, a whole-module import or a macro body of another component that can take the item
//!   without its name (the module of the item is open, or an open module takes the item);
//! - an import of another component with the name of the item whose route is not proven;
//! - a type (a class, an alias or a macro): a signature of a used item may need it, and the
//!   collector states no resolved signature types.
//!
//! A PASS needs every public symbol: a profile whose collector does not state its symbol facts
//! in full gives FAIL or UNKNOWN (`limits.rs`).

use std::collections::{HashMap, HashSet};

use archkeel_contract::{PublicItemKind, UnusedPublic};
use archkeel_facts::envelope::Facts;
use archkeel_facts::{Record, Section, SymbolFact};

use crate::model::Model;
use crate::ownership::{in_scope, owner_of};
use crate::reason::{Hygiene, Reason};

/// One public module-level item of the reply.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PublicItem {
    /// The module that defines it.
    pub module: String,
    /// Its name.
    pub name: String,
    /// Its kind, as the symbol facts name it.
    pub kind: PublicItemKind,
    /// The evidence of its definition.
    pub evidence: Vec<String>,
}

/// The public module-level items of the symbol facts, in reply order.
pub(crate) fn items(facts: &Facts) -> Vec<PublicItem> {
    let records: &[Record<SymbolFact>] = facts
        .sections
        .iter()
        .find_map(|section| match section {
            Section::Symbols(records) => Some(records.as_slice()),
            _ => None,
        })
        .unwrap_or(&[]);
    records.iter().filter_map(item).collect()
}

fn item(record: &Record<SymbolFact>) -> Option<PublicItem> {
    use PublicItemKind as K;
    let (kind, module, name, parent, visibility) = match &record.data {
        SymbolFact::Class(d) => (K::Class, &d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::Function(d) => (K::Function, &d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::Method(_) => return None,
        SymbolFact::Constant(d) => (K::Constant, &d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::TypeAlias(d) => (K::TypeAlias, &d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::Binding(d) => (K::Binding, &d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::Alias(d) => (K::Alias, &d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::DynamicBinding(d) => {
            (K::DynamicBinding, &d.module, &d.name, &d.parent, &d.visibility_detail)
        }
        SymbolFact::StaticConstant(d) => {
            (K::StaticConstant, &d.module, &d.name, &d.parent, &d.visibility_detail)
        }
        SymbolFact::Macro(d) => (K::Macro, &d.module, &d.name, &d.parent, &d.visibility_detail),
    };
    (parent.is_none() && visibility.kind == "public").then(|| PublicItem {
        module: module.as_str().to_owned(),
        name: name.clone(),
        kind,
        evidence: record.evidence_ids.iter().map(|id| id.as_str().to_owned()).collect(),
    })
}

/// How the rule judges one public item that no other component is proven to use.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Unused {
    /// No user, and the facts show every way a user could take it: a violation.
    Fail,
    /// No proven user, but a use may exist that the facts do not show.
    Undecided(&'static str),
}

/// The items of one rule that no other component is proven to use, in reply order.
pub fn unused<'m>(model: &'m Model, rule: &UnusedPublic) -> Vec<(&'m PublicItem, Unused)> {
    let Some(items) = model.graph().published() else {
        return Vec::new();
    };
    let users = Users::of(model);
    let exempt: HashSet<&str> = rule.external_users().iter().map(|u| u.symbol().as_str()).collect();
    let kinds = rule.item_kinds();
    items
        .iter()
        .filter(|item| {
            model.selects(&item.module)
                && in_scope(&item.module, rule.source().as_text())
                && (kinds.is_empty() || kinds.contains(&item.kind))
                && !exempt.contains(format!("{}:{}", item.module, item.name).as_str())
        })
        .filter_map(|item| users.judge(item).map(|judged| (item, judged)))
        .collect()
}

/// The receipt of the rule: no item is undecided. An undecided item holds back a PASS and decides
/// nothing; a violation stays FAIL.
pub(crate) fn receipt(model: &Model, rule: &UnusedPublic) -> Result<(), Reason> {
    let undecided: Vec<(&PublicItem, &str)> = unused(model, rule)
        .into_iter()
        .filter_map(|(item, judged)| match judged {
            Unused::Undecided(why) => Some((item, why)),
            Unused::Fail => None,
        })
        .collect();
    let Some((first, why)) = undecided.first() else {
        return Ok(());
    };
    let detail = format!(
        "{} public items have no proven user, and a use may exist that the facts do not show; \
         the first is {}:{} ({why})",
        undecided.len(),
        first.module,
        first.name
    );
    Err(Reason::Hygiene(Hygiene::new("unused_public_undecided", detail)))
}

/// The uses that cross a component, read once for all items of a rule.
struct Users {
    /// Each `module.name` that an import of another component names.
    named: HashSet<String>,
    /// The modules whose names another component may take without naming them: the target of a
    /// glob, of a whole-module import whose names the collector does not know, or of a macro
    /// body, and each module that such a module takes in by a glob.
    open: HashSet<String>,
    /// Each `module.name` that an open module takes by name: a use through the open module may
    /// reach it.
    reached: HashSet<String>,
    /// Each name that an import of another component names through a route it does not prove.
    unproven: HashSet<String>,
}

impl Users {
    fn of(model: &Model) -> Self {
        let components = model.components();
        let mut owners = HashMap::new();
        let mut owner = |module: &str| {
            *owners
                .entry(module.to_owned())
                .or_insert_with(|| owner_of(components, module))
        };
        let mut crossing = |source: &str, target: &str| {
            let from = owner(source);
            from.is_none() || from != owner(target)
        };
        let mut users = Users::default_sets();
        // AD-604: a profile that writes each use through a whole-module import as a record of
        // its own binds no name with that import.
        let namespace_uses = model.graph().observed().namespace_uses;
        let imports = model.graph().imports();
        for import in imports {
            let target = import.target_module();
            if !(crossing(import.source_module(), target) || import.other_crate()) {
                continue;
            }
            match import.symbol() {
                Some("*") => drop(users.open.insert(target.to_owned())),
                None if !namespace_uses => drop(users.open.insert(target.to_owned())),
                None => {}
                Some(name) => {
                    users.named.insert(format!("{target}.{name}"));
                    users.named.extend(import.reexport_chain().iter().cloned());
                    if !import.route_complete() || !import.symbols_known() {
                        users.unproven.insert(name.to_owned());
                    }
                }
            }
        }
        for (source, target) in model.graph().macro_bodies() {
            if crossing(source, target) {
                users.open.insert(target.clone());
            }
        }
        users.close(imports);
        users
    }

    fn default_sets() -> Self {
        Users {
            named: HashSet::new(),
            open: HashSet::new(),
            reached: HashSet::new(),
            unproven: HashSet::new(),
        }
    }

    /// Follow each import of an open module: a glob opens its target, a name is reached.
    fn close(&mut self, imports: &[crate::imports::Import]) {
        loop {
            let mut added = Vec::new();
            for import in imports.iter().filter(|i| self.open.contains(i.source_module())) {
                let target = import.target_module();
                match import.symbol() {
                    Some("*") | None if !self.open.contains(target) => added.push(target.to_owned()),
                    Some("*") | None => {}
                    Some(name) => {
                        self.reached.insert(format!("{target}.{name}"));
                        self.reached.extend(import.reexport_chain().iter().cloned());
                    }
                }
            }
            if added.is_empty() {
                break;
            }
            self.open.extend(added);
        }
    }

    fn judge(&self, item: &PublicItem) -> Option<Unused> {
        use PublicItemKind as K;
        let key = format!("{}.{}", item.module, item.name);
        if self.named.contains(&key) {
            return None;
        }
        Some(if self.open.contains(&item.module) || self.reached.contains(&key) {
            Unused::Undecided("another component may take it through a glob, a module or a macro")
        } else if self.unproven.contains(&item.name) {
            Unused::Undecided("another component imports its name through a route that is not proven")
        } else if matches!(item.kind, K::Class | K::TypeAlias | K::Alias | K::Macro) {
            Unused::Undecided("a signature of a used item may need it; the facts state no signature types")
        } else {
            Unused::Fail
        })
    }
}
