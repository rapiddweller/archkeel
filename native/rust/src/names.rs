// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What each import record names (AD-604, AD-608): the item, the type of a member, a glob or a
//! whole module, the publication route of the item, and the name that a re-export publishes
//! outside its crate. `module_edges.rs` and `edges.rs` write the records; this file names them.

use archkeel_facts::{ImportFact, Record};

use crate::modules::{Edge, Index};
use crate::routes::{route, Publications, Route};
use crate::scan::{Reference, Via};

/// What an import names (AD-604): the item, the type of a member, a glob (`*`) or a whole module
/// (`None`), with the publication route of the item.
pub(crate) struct ImportName {
    symbol: Option<String>,
    route: Route,
}

impl ImportName {
    /// A whole module or crate: no name of it, and no route.
    pub(crate) fn whole() -> Self {
        ImportName {
            symbol: None,
            route: Route::none(),
        }
    }

    /// A glob names every name of its module, and the scan does not know which one a use takes.
    pub(crate) fn glob() -> Self {
        ImportName {
            symbol: Some("*".to_owned()),
            route: Route::none(),
        }
    }
}

pub(crate) fn named(
    index: &Index<'_>,
    roots: &mut Publications,
    edge: &Edge,
    via: &Via,
) -> ImportName {
    if matches!(via, Via::Glob { .. }) {
        return ImportName::glob();
    }
    // A member of an `impl` block: the type in the module of the block, and its publications.
    if let Some((at, ty)) = &edge.member_of {
        let route = if edge.lexical == edge.module {
            roots.member(index, &edge.module, at, ty)
        } else {
            Route::none()
        };
        return ImportName {
            symbol: Some(ty.clone()),
            route,
        };
    }
    item(index, &edge.lexical, edge.symbol.as_deref())
}

/// The item that a path names after the module `lexical`, and its route; `None` for a module.
pub(crate) fn item(index: &Index<'_>, lexical: &str, symbol: Option<&str>) -> ImportName {
    match symbol.filter(|name| !name.is_empty()) {
        Some(name) => ImportName {
            symbol: Some(name.to_owned()),
            route: route(index, lexical, name),
        },
        None => ImportName {
            symbol: None,
            route: Route::none(),
        },
    }
}

/// The name that a `use` leaf publishes outside its crate (AD-608): a `pub use` at module level of
/// the root of a library crate. A glob publishes names that the scan does not list (`*`). A leaf
/// with a restricted visibility (`pub(crate)`) publishes nothing outside the crate.
pub(crate) fn published(index: &Index<'_>, module: &str, reference: &Reference) -> Option<String> {
    let frame = index.frame(module)?;
    let krate = frame.krate();
    let root = krate
        .primary
        .as_ref()
        .is_some_and(|root| root.module == module);
    if !(krate.library && root) || frame.lexical_at(&reference.scope) != module {
        return None;
    }
    match &reference.via {
        Via::Use {
            binding: Some(name),
            reexport: true,
            block: false,
        } if name != "_" && !frame.module.scan.restricted_bindings.contains(name) => {
            Some(name.clone())
        }
        Via::Glob {
            reexport: true,
            block: false,
        } => Some("*".to_owned()),
        _ => None,
    }
}

/// The record with the name that it imports: the collector reads the name of each import.
pub(crate) fn with_name(mut record: Record<ImportFact>, named: ImportName) -> Record<ImportFact> {
    let data = record.data.data_mut();
    data.symbol = named.symbol;
    data.symbols_known = true;
    let Route { hops, complete } = named.route;
    data.route_complete = (!hops.is_empty() && !complete).then_some(false);
    data.reexport_chain = (!hops.is_empty()).then_some(hops);
    record
}
