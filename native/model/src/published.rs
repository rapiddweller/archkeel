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
//! - a type (a class, an alias or a macro) in a language whose public signatures need public
//!   types: a signature of a used item may need it, and no collector states resolved signature
//!   types. Where the visibility is a name convention, such a type is judged by its name like any
//!   other item (owner decision).
//!
//! A PASS needs every public symbol: a profile whose collector does not state its symbol facts
//! in full gives FAIL or UNKNOWN (`limits.rs`).

use std::collections::{HashMap, HashSet};

use archkeel_contract::{PublicItemKind, UnusedPublic};

use crate::model::Model;
use crate::ownership::{in_scope, owner_of};
use crate::published_items::PublicItem;
use crate::reason::{Hygiene, Reason};

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
    let exempt: HashSet<&str> = rule
        .external_users()
        .iter()
        .map(|u| u.symbol().as_str())
        .collect();
    let kinds = rule.item_kinds();
    items
        .iter()
        .filter(|item| {
            model.selects(&item.module)
                && in_scope(&item.module, rule.source().as_text())
                // AD-718: an item of no kind whose name is not read may be of any kind.
                && (kinds.is_empty()
                    || kinds.contains(&item.kind)
                    || (!item.named && item.kind == PublicItemKind::DynamicBinding))
                && !exempt.contains(format!("{}:{}", item.module, item.name).as_str())
        })
        .filter_map(|item| users.judge(item).map(|judged| (item, judged)))
        .collect()
}

/// The receipt of the rule: no item is undecided, and whether the rule selects a module. An
/// undecided item holds back a PASS and decides nothing; a violation stays FAIL.
pub(crate) fn receipt(model: &Model, rule: &UnusedPublic) -> Result<bool, Reason> {
    let undecided: Vec<(&PublicItem, &str)> = unused(model, rule)
        .into_iter()
        .filter_map(|(item, judged)| match judged {
            Unused::Undecided(why) => Some((item, why)),
            Unused::Fail => None,
        })
        .collect();
    let Some((first, why)) = undecided.first() else {
        return Ok(!model.source_modules(rule.source().as_text()).is_empty());
    };
    let detail = format!(
        "{} public items have no proven user, and a use may exist that the facts do not show; \
         the first is {}:{} ({why})",
        undecided.len(),
        first.module,
        first.name
    );
    Err(Reason::Hygiene(Hygiene::new(
        "unused_public_undecided",
        detail,
    )))
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
    /// A public signature of the language needs public types, so a used signature may need a type
    /// that no other component names (AD-670).
    signatures: bool,
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
        let mut users = Users::default_sets(model.graph().observed().signatures_need_public_types);
        // AD-604: a profile that writes each use through a whole-module import as a record of
        // its own binds no name with that import.
        let namespace_uses = model.graph().observed().namespace_uses;
        let imports = model.graph().imports();
        for import in imports {
            let target = import.target_module();
            if !(crossing(import.source_module(), target) || import.other_crate()) {
                continue;
            }
            users.note(import, namespace_uses);
        }
        for (source, target) in model.graph().macro_bodies() {
            if crossing(source, target) {
                users.open.insert(target.clone());
            }
        }
        users.close(imports);
        users
    }

    /// Record the use that one import makes of its target.
    fn note(&mut self, import: &crate::imports::Import, namespace_uses: bool) {
        let target = import.target_module();
        match import.symbol() {
            Some("*") => drop(self.open.insert(target.to_owned())),
            None if !namespace_uses => drop(self.open.insert(target.to_owned())),
            // A module `P.x` and an item `x` of `P` share a name in two namespaces, and a
            // whole-module import of `P.x` may name the item too (`mod reply; pub fn reply`).
            None => drop(self.reached.insert(target.to_owned())),
            Some(name) => {
                self.named.insert(format!("{target}.{name}"));
                self.named.extend(import.reexport_chain().iter().cloned());
                if !import.route_complete() || !import.symbols_known() {
                    self.unproven.insert(name.to_owned());
                }
            }
        }
    }

    /// The module that an import of an open module opens, or none when the import names an item
    /// (which it reaches instead).
    fn follow(&mut self, import: &crate::imports::Import) -> Option<String> {
        let target = import.target_module();
        match import.symbol() {
            Some("*") | None => (!self.open.contains(target)).then(|| target.to_owned()),
            Some(name) => {
                self.reached.insert(format!("{target}.{name}"));
                self.reached.extend(import.reexport_chain().iter().cloned());
                None
            }
        }
    }

    fn default_sets(signatures: bool) -> Self {
        Users {
            named: HashSet::new(),
            open: HashSet::new(),
            reached: HashSet::new(),
            unproven: HashSet::new(),
            signatures,
        }
    }

    /// Follow each import of an open module: a glob opens its target, a name is reached.
    fn close(&mut self, imports: &[crate::imports::Import]) {
        loop {
            let mut added = Vec::new();
            let open: Vec<_> = imports
                .iter()
                .filter(|i| self.open.contains(i.source_module()))
                .collect();
            for import in open {
                added.extend(self.follow(import));
            }
            if added.is_empty() {
                break;
            }
            self.open.extend(added);
        }
    }

    fn judge(&self, item: &PublicItem) -> Option<Unused> {
        if !item.named {
            return Some(Unused::Undecided(
                "a macro call gives its name, which the collector does not read",
            ));
        }
        let key = format!("{}.{}", item.module, item.name);
        if self.named.contains(&key) {
            return None;
        }
        Some(
            if self.open.contains(&item.module) || self.reached.contains(&key) {
                Unused::Undecided(
                    "another component may take it through a glob, a module or a macro",
                )
            } else if self.unproven.contains(&item.name) {
                Unused::Undecided(
                    "another component imports its name through a route that is not proven",
                )
            } else if self.signatures
                && matches!(
                    item.kind,
                    PublicItemKind::Class
                        | PublicItemKind::TypeAlias
                        | PublicItemKind::Alias
                        | PublicItemKind::Macro
                )
            {
                Unused::Undecided(
                    "a signature of a used item may need it; the facts state no signature types",
                )
            } else {
                Unused::Fail
            },
        )
    }
}
