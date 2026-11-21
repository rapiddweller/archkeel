// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The publication route of a name (AD-604): each module that publishes the name on the way from
//! the module that a path names to the module that defines it, as `module.name` hops.
//!
//! Each hop is true: the path, or the `use` leaf of the hop before it, names that name in that
//! module, and rustc resolved it. The route is complete only when each step is certain, by the
//! rules of AD-544 (`cross_outcome`): no attribute can swap the file of the module, the file
//! declares the name once (in any namespace, at any depth), no macro call in item place can add a
//! declaration, and the name is a definition of the module or the one module-level `use` leaf
//! that binds it with no attribute that can remove it. A definition ends the route, and so does a
//! leaf into a crate outside the workspace, which the scan does not read. At any other step (a
//! glob or a macro may give the name, a leaf that names a module, the step limit) the route stops
//! and is not complete: a later hop may follow. An item of an inline module has no hop, because
//! a hop names a file module.

use crate::definitions::{Form, Owner};
use std::collections::{BTreeMap, BTreeSet};

use crate::modules::{binds_nothing, Frame, Index, Outcome, MAX_HOPS};
use crate::resolve::{classify, Found, Named};
use crate::scan::{Reference, Via};

/// The hops of a route, and whether the scan proves each step to its end.
pub(crate) struct Route {
    pub hops: Vec<String>,
    pub complete: bool,
    /// This package can publish an item that a different package defines.
    pub external_package: Option<String>,
}

impl Route {
    /// No route: the import names no item, or names it where no hop can stand.
    pub(crate) fn none() -> Self {
        Route {
            hops: Vec::new(),
            complete: true,
            external_package: None,
        }
    }
}

/// Where a `use` leaf takes a name.
enum Next {
    /// A name of a module of the workspace: its lexical module and the name there.
    Item(String, String),
    /// The sysroot, which does not give an external dependency.
    Sysroot,
    /// A package that the scan does not read.
    External { package: String, registry: bool },
}

/// The route of `name` in the lexical module `at`.
pub(crate) fn route(index: &Index<'_>, at: &str, name: &str) -> Route {
    route_in(index, at, name, false)
}

/// The route of `name` when it must end at a type (AD-608). A macro call in item place cannot
/// add a second type of the name: it would collide with the `use` or the definition of the name
/// (E0255, E0428). So the macro check is not needed; a route that ends at another item is not
/// complete.
fn type_route(index: &Index<'_>, at: &str, name: &str) -> Route {
    route_in(index, at, name, true)
}

fn route_in(index: &Index<'_>, at: &str, name: &str, of_type: bool) -> Route {
    let mut hops = Vec::new();
    let (mut at, mut name) = (at.to_owned(), name.to_owned());
    let stop = |hops: Vec<String>, complete: bool| Route {
        hops,
        complete,
        external_package: None,
    };
    loop {
        let Some(frame) = index.file_of(&at).and_then(|file| index.frame(file)) else {
            return stop(hops, false);
        };
        if frame.module.module != at || hops.len() > MAX_HOPS {
            return stop(hops, false);
        }
        hops.push(format!("{at}.{name}"));
        let scan = &frame.module.scan;
        let opaque = frame.module.gated && frame.module.gates.is_none();
        if !opaque && !of_type && defined_here(index, frame, &name) {
            return stop(hops, true);
        }
        if opaque || (scan.module_macros && !of_type) {
            return stop(hops, false);
        }
        if of_type && !scan.counts.contains_key(&name) {
            return stop(hops, macro_type_here(index, frame, &name));
        }
        if scan.counts.get(&name) != Some(&1) {
            return stop(hops, false);
        }
        let defined = scan.definitions.iter().find(|d| {
            d.name == name && d.owner == Owner::Module && frame.lexical_at(&d.scope) == at
        });
        if let Some(definition) = defined {
            let a_type = matches!(definition.form, Form::Struct | Form::Enum | Form::Trait);
            return stop(hops, a_type || !of_type);
        }
        let [leaf] = frame.bound(&name) else {
            return stop(hops, false);
        };
        if scan.conditional_bindings.contains(&name)
            || !matches!(leaf.via, Via::Use { block: false, .. })
            || frame.lexical_at(&leaf.scope) != at
        {
            return stop(hops, false);
        }
        match next(index, frame, leaf) {
            Some(Next::Item(module, item)) => (at, name) = (module, item),
            Some(Next::Sysroot) => return stop(hops, true),
            Some(Next::External { package, registry }) => {
                return Route {
                    hops,
                    complete: registry,
                    external_package: Some(package),
                }
            }
            None => return stop(hops, false),
        }
    }
}

/// Whether the name is defined in the file, so the route ends there (AD-608, AD-614). No `use`
/// leaf, glob or `extern crate` of the file binds the name, so only a definition gives it: a written
/// one, two under `cfg`, or one of a macro call in item place. Each call in item place is a call by
/// its plain name of the one crate-wide `macro_rules!` of that name in the crate. The call writes
/// no import, and the expansion writes none at item level and calls only such macros there
/// (`macro_items::item_level`). Such a call can add a definition, never a re-export.
fn defined_here(index: &Index<'_>, frame: &Frame<'_>, name: &str) -> bool {
    let scan = &frame.module.scan;
    if !frame.bound(name).is_empty()
        || frame.globs().next().is_some()
        || !scan.extern_crates.is_empty()
        || !scan.self_aliases.is_empty()
    {
        return false;
    }
    binds_nothing(index, frame)
}

/// Whether `name` has no written declaration or `use` in `frame`, and every module-level macro
/// call of `frame` can declare `name` only as a nominal type (`struct`, `enum`, `trait`), with at
/// least one call witnessing `name` (AD-1039).
fn macro_type_here(index: &Index<'_>, frame: &Frame<'_>, name: &str) -> bool {
    if !defined_here(index, frame, name) {
        return false;
    }
    let crate_index = frame.module.crate_index;
    let mut witnessed = false;
    for call in frame
        .module
        .scan
        .macro_calls
        .iter()
        .filter(|call| call.fills && frame.lexical_at(&call.scope) == frame.module.module)
    {
        let defs: Vec<_> = index
            .frames()
            .filter(|other| other.module.crate_index == crate_index)
            .flat_map(|other| other.module.scan.macro_defs.iter())
            .filter(|def| def.name == call.name)
            .collect();
        let [def] = defs.as_slice() else {
            // A `std` `NO_BIND` macro is an expression macro and declares no item; any other case
            // was already rejected by `defined_here`.
            continue;
        };
        if !def.item_level.calls.iter().all(|inner| inner == &def.name) {
            return false;
        }
        let (items, opaque) =
            crate::macro_items::published(&def.item_level, &def.name, &call.public.head);
        if opaque {
            return false;
        }
        for (kind, item_name, _) in &items {
            let is_nominal = matches!(kind.as_str(), "struct" | "enum" | "trait");
            let exact = item_name == name;
            let meta = item_name.starts_with('$');
            if (exact || meta || item_name.is_empty()) && !is_nominal {
                return false;
            }
            if is_nominal && (exact || (meta && call.idents.contains(name))) {
                witnessed = true;
            }
        }
    }
    witnessed
}

/// The module and the name that a `use` leaf of `frame` names, by the rules of the edges: a
/// first segment that names a crate is that crate, any other path goes to the module resolver.
fn next(index: &Index<'_>, frame: &Frame<'_>, leaf: &Reference) -> Option<Next> {
    let first = leaf.names.first()?;
    let alias = index.is_alias(&frame.module.module, first);
    let found = classify(
        first,
        frame.krate(),
        &frame.module.scan.shadows,
        leaf.absolute,
    )
    .filter(|_| !alias);
    let outcome = match found {
        Some(Found::Edge(Named::Package(package))) => {
            let Some(root) = index.workspace().primary_of(&package) else {
                return Some(Next::External {
                    package,
                    registry: false,
                });
            };
            index.reach(&root.module, leaf.names.get(1..)?)
        }
        Some(Found::Edge(Named::Registry(package))) => {
            return Some(Next::External {
                package,
                registry: true,
            });
        }
        Some(Found::Edge(Named::Sysroot(_))) => return Some(Next::Sysroot),
        Some(Found::Shadowed) => return None,
        None => index.resolve(frame, leaf),
    };
    match outcome {
        Outcome::Edge(edge) => {
            let item = edge.symbol.filter(|name| !name.is_empty())?;
            // The item must be the last segment: `use a::T::V` names a variant of `T`.
            (leaf.names.last() == Some(&item)).then_some(Next::Item(edge.lexical, item))
        }
        Outcome::None | Outcome::Unknown(_) => None,
    }
}

/// The names that the root of each crate target publishes to other crates, by the last hop of
/// their route (AD-608): `pub use model::Model;` in the root publishes `root.Model` for the
/// definition `model.Model`. Only a leaf that is public outside the crate counts.
#[derive(Default)]
pub(crate) struct Publications {
    roots: BTreeMap<String, Published>,
}

#[derive(Default)]
struct Published {
    by_definition: BTreeMap<String, Vec<String>>,
    /// A leaf of the root whose route the scan does not prove may publish any definition.
    partial: bool,
}

impl Publications {
    /// The route of a member of the type `name`, which the lexical module `at` defines, in an
    /// `impl` block of the module `block` (#953): the type in the module of the block, each name
    /// of its crate root that publishes it, and its definition. A use passes when one is public.
    pub(crate) fn member(&mut self, index: &Index<'_>, block: &str, at: &str, name: &str) -> Route {
        let definition = format!("{at}.{name}");
        let mut hops = vec![format!("{block}.{name}")];
        let frame = index.file_of(at).and_then(|file| index.frame(file));
        let Some(frame) = frame.filter(|frame| frame.module.module == at) else {
            return Route {
                hops,
                complete: false,
                external_package: None,
            };
        };
        let root = frame.root();
        let published = self
            .roots
            .entry(root.to_owned())
            .or_insert_with(|| published(index, root));
        hops.extend(
            published
                .by_definition
                .get(&definition)
                .into_iter()
                .flatten()
                .cloned(),
        );
        hops.push(definition);
        let mut seen = BTreeSet::new();
        hops.retain(|hop| seen.insert(hop.clone()));
        Route {
            hops,
            complete: !published.partial,
            external_package: None,
        }
    }
}

fn published(index: &Index<'_>, root: &str) -> Published {
    let mut found = Published::default();
    let Some(frame) = index.frame(root) else {
        found.partial = true;
        return found;
    };
    let scan = &frame.module.scan;
    for leaf in frame.leaves() {
        let Via::Use {
            binding: Some(name),
            reexport: true,
            block: false,
        } = &leaf.via
        else {
            continue;
        };
        if scan.restricted_bindings.contains(name) || frame.lexical_at(&leaf.scope) != root {
            continue;
        }
        let Route { hops, complete, .. } = type_route(index, root, name);
        match hops.last() {
            Some(last) if complete => {
                let entry = found.by_definition.entry(last.clone()).or_default();
                entry.push(format!("{root}.{name}"));
            }
            _ => found.partial = true,
        }
    }
    found
}

#[cfg(test)]
mod tests {
    use crate::collect::tests::run;

    fn root_publication_complete(lib_extra: &str, types_src: &str) -> bool {
        let lib = format!("mod a;\nmod b;\nmod types;\n{lib_extra}");
        let files = [
            (
                "crates/app/Cargo.toml",
                "[package]\nname = \"app\"\nedition = \"2021\"\n",
            ),
            ("crates/app/src/lib.rs", lib.as_str()),
            (
                "crates/app/src/b.rs",
                "pub struct S;\nimpl S { pub fn m(&self) {} }\n",
            ),
            (
                "crates/app/src/a.rs",
                "pub fn f(s: &crate::b::S) { s.m(); }\n",
            ),
            ("crates/app/src/types.rs", types_src),
        ];
        let facts = run(&files, false);
        let call_edge = facts
            .imports
            .iter()
            .map(|record| record.data.data())
            .find(|data| {
                data.source_module.as_str() == "ns.app.a"
                    && data.target_module.as_str() == "ns.app.b"
            })
            .expect("expected method-call edge from a to b");
        call_edge.route_complete != Some(false)
    }

    #[test]
    fn type_route_proves_a_single_nominal_type_definition() {
        assert!(root_publication_complete(
            "pub use types::Item;\n",
            "pub struct Item;\n",
        ));
    }

    #[test]
    fn type_route_rejects_a_type_alias() {
        assert!(!root_publication_complete(
            "pub use types::Alias;\n",
            "pub type Alias = u64;\n",
        ));
    }

    #[test]
    fn type_route_rejects_multiple_cfg_gated_bindings() {
        assert!(!root_publication_complete(
            "pub use types::Item;\n",
            "#[cfg(unix)]\npub struct Item;\n#[cfg(not(unix))]\npub struct Item;\n",
        ));
    }

    #[test]
    fn type_route_proves_a_macro_defined_nominal_type_and_rejects_a_macro_alias() {
        let nominal_macro = concat!(
            "macro_rules! mk_enum {\n",
            "    ($name:ident) => { pub enum $name {} };\n",
            "}\n",
            "mk_enum!(Made);\n",
        );
        assert!(root_publication_complete(
            "pub use types::Made;\n",
            nominal_macro,
        ));

        let alias_macro = concat!(
            "macro_rules! mk_alias {\n",
            "    ($name:ident) => { pub type $name = u64; };\n",
            "}\n",
            "mk_alias!(MadeAlias);\n",
        );
        assert!(!root_publication_complete(
            "pub use types::MadeAlias;\n",
            alias_macro,
        ));
    }
}
