// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The publication surface of one import or export directive (AD-749): which names of the
//! namespace of its target it binds, the first hop of each route, and whether a library publishes
//! outside its package.
//!
//! The Dart rules that this reads:
//!
//! - an `import` or `export` without `show` binds the whole export namespace of its target, less
//!   each `hide` name; the survey reads no use of those names;
//! - the combinators apply in their order: `show` keeps only its names, `hide` removes its names;
//! - the export namespace of a library is each public declaration of the library and its parts,
//!   and each name that an `export` of the library or of a part adds;
//! - a library below `lib/` but not below `lib/src/` is a library that another package imports
//!   (the package layout of `dart.dev`); a library below `lib/src/` is the implementation of the
//!   package, and no other directory of the package is importable from another package.
//!
//! A file with a syntax error has no directive here: the index gives it no module (`Kind`), so a
//! `show` list that the parse reads only in part never gives a record.

use std::collections::{BTreeSet, HashSet};

use archkeel_facts::data::ImportData;

use super::index::{Index, Kind, Owners};
use crate::syntax::{Combinator, Directive, DirectiveKind};

/// What one directive binds of the namespace of its target.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Binding {
    /// The names that `show` keeps after each combinator, sorted.
    Names(Vec<String>),
    /// The whole namespace, less the `hide` names: no `show` at all, or a `show` whose names are
    /// all hidden again (4.0.1 writes both as an unknown binding).
    Namespace,
}

impl Binding {
    /// The binding of `directive`, by its combinators in their order.
    pub(crate) fn of(directive: &Directive) -> Self {
        let mut shown: Option<BTreeSet<&str>> = None;
        let mut hidden: BTreeSet<&str> = BTreeSet::new();
        for (mode, names) in &directive.combinators {
            let names: BTreeSet<&str> = names.iter().map(String::as_str).collect();
            match (mode, &mut shown) {
                (Combinator::Show, Some(kept)) => kept.retain(|name| names.contains(name)),
                (Combinator::Show, None) => {
                    shown = Some(names.difference(&hidden).copied().collect());
                }
                (Combinator::Hide, Some(kept)) => kept.retain(|name| !names.contains(name)),
                (Combinator::Hide, None) => hidden.extend(names),
            }
        }
        match shown {
            Some(kept) if !BTreeSet::is_empty(&kept) => {
                Binding::Names(kept.into_iter().map(str::to_owned).collect())
            }
            _ => Binding::Namespace,
        }
    }

    /// The name of each record: one for each bound name, or one record without a name.
    pub(crate) fn names(&self) -> Vec<Option<&str>> {
        match self {
            Binding::Names(names) => names.iter().map(String::as_str).map(Some).collect(),
            Binding::Namespace => vec![None],
        }
    }

    /// Write the binding of one record. `name` is one of `names`; `complete` is true when the
    /// target library declares each name of its namespace itself (`Surface::declares`).
    pub(crate) fn state(
        &self,
        data: &mut ImportData,
        name: Option<&str>,
        target: &str,
        complete: bool,
    ) {
        // A later hop through an `export` of the target may publish a name of another module.
        data.route_complete = (!complete).then_some(false);
        if let (Binding::Names(_), Some(name)) = (self, name) {
            data.symbol = Some(name.to_owned());
            data.binding = Some(name.to_owned());
            data.symbols_known = true;
            data.reexport_chain = Some(vec![format!("{target}.{name}")]);
        }
        // A namespace keeps no symbol and `symbols_known` false: it binds each name of the
        // target, and the survey reads no use of them (the interface rule reads AD-97).
    }
}

/// The local libraries that declare every name of their export namespace: no `export` in the
/// library or in one of its parts.
pub(crate) struct Surface {
    exporting: HashSet<usize>,
}

impl Surface {
    /// The surface of the libraries of `index`.
    pub(crate) fn of(index: &Index<'_>, owners: &Owners) -> Self {
        let exports = |at: usize| {
            index.syntax[at].as_ref().is_some_and(|syntax| {
                syntax
                    .directives
                    .iter()
                    .any(|directive| directive.kind == DirectiveKind::Export)
            })
        };
        let mut exporting = HashSet::new();
        for (at, kind) in index.kinds.iter().enumerate() {
            let library = match kind {
                Kind::Library => Some(at),
                Kind::Part => owners.get(&at).copied(),
                Kind::Unknown => None,
            };
            if let Some(library) = library.filter(|_| exports(at)) {
                exporting.insert(library);
            }
        }
        Self { exporting }
    }

    /// True when the selected library at `rel` re-exports nothing, so its namespace holds only
    /// its own declarations.
    pub(crate) fn declares(&self, index: &Index<'_>, rel: &str) -> bool {
        index.by_rel.get(rel).is_some_and(|at| {
            index.kinds[*at] == Kind::Library
                && index.syntax[*at].is_some()
                && !self.exporting.contains(at)
        })
    }
}

/// True when the library at `rel` is importable from another package: below `lib/`, not below
/// `lib/src/`.
pub(crate) fn published(rel: &str) -> bool {
    rel.strip_prefix("lib/")
        .is_some_and(|rest| !rest.starts_with("src/"))
}

#[cfg(test)]
#[path = "binding_tests.rs"]
mod tests;
