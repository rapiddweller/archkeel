// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of the edges between the modules of one crate: one `import` or `reexport` record
//! for each distinct path of a module that names another module of its crate, and one gap for
//! each path that the scan cannot resolve. The resolution is in `modules.rs`.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_facts::{ImportFact, Record};

use crate::builder::{import_record, Builder};
use crate::crates::Root;
use crate::definitions::MethodCall;
use crate::modules::{Edge, Index, Outcome};
use crate::routes::{route, Publications, Route};
use crate::scan::{MacroCall, MacroDef, Reference, Site, Via};
use crate::tree::Module;

/// The `macro_rules!` definitions of each crate, by name: the module, and the definition.
type Defs<'a> = BTreeMap<(usize, &'a str), Vec<(&'a Module, &'a MacroDef)>>;

/// The definitions of `name` that a call sees: each crate-wide one, and each one of a block that
/// holds the call after the definition.
fn visible<'a>(
    defs: &Defs<'a>,
    module: &Module,
    call: &MacroCall,
    name: &str,
) -> Vec<(&'a Module, &'a MacroDef)> {
    let all = defs.get(&(module.crate_index, name)).into_iter().flatten();
    all.filter(|(owner, def)| {
        def.local
            .is_none_or(|local| owner.module == module.module && local.sees(&call.site))
    })
    .copied()
    .collect()
}

impl Builder {
    pub(crate) fn module_edge(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        reference: &Reference,
    ) {
        let Some(frame) = index.frame(&module.module) else {
            return;
        };
        // A glob names a module, also by one name (`use child::*;`): an empty last name lets the
        // path end at that module, as `through_glob` does (AD-608).
        let mut glob = None;
        if matches!(reference.via, Via::Glob { .. }) {
            let mut names = reference.names.clone();
            names.push(String::new());
            glob = Some(Reference {
                names,
                ..reference.clone()
            });
        }
        match index.resolve(frame, glob.as_ref().unwrap_or(reference)) {
            // A body path from the crate name (`::app::b`) needs `extern crate self as app`.
            Outcome::None if reference.absolute && reference.in_macro.is_some() => {
                let reason = "A macro_rules! body holds a path from the name of its own crate";
                self.unreadable(module, reference, reason.to_owned());
            }
            // A path inside one crate that no module edge names: a local outcome.
            Outcome::None => self.ended += 1,
            Outcome::Unknown(reason) => self.unreadable(module, reference, reason),
            Outcome::Edge(edge) => match &reference.in_macro {
                None => self.module_import(index, module, reference, &edge),
                Some(_) => self.macro_use(index, module, reference, edge),
            },
        }
    }

    /// A path in a `macro_rules!` body that starts at `crate` names the same module wherever the
    /// macro expands, so each call of the macro gets the edge (`macro_calls`). The definition keeps
    /// its own edge as `macro_body`, which no cycle or layer rule reads. Any other path in a body
    /// is relative to the place of the call: the scan does not know it, and each call is UNKNOWN.
    fn macro_use(&mut self, index: &Index<'_>, module: &Module, reference: &Reference, edge: Edge) {
        if reference.names.first().map(String::as_str) == Some("crate") {
            self.module_import(index, module, reference, &edge);
            let key = (module.module.clone(), reference.macro_id);
            self.macro_uses
                .entry(key)
                .or_default()
                .push((edge, reference.clone()));
            return;
        }
        let reason =
            "A macro_rules! body holds a module path that is relative to the place of the call";
        self.unreadable(module, reference, reason.to_owned());
    }

    /// A path that the scan cannot read is UNKNOWN here. In a macro body, each call is UNKNOWN too.
    fn unreadable(&mut self, module: &Module, reference: &Reference, reason: String) {
        let evidence = self.cite(&module.rel, &reference.site);
        self.gap(&reason, Some(&evidence), &module.module);
        self.unread_macro(module, reference, reason);
        self.ended += 1;
    }

    /// The body of a macro holds a path that the scan cannot read: each call of it is UNKNOWN.
    fn unread_macro(&mut self, module: &Module, reference: &Reference, reason: String) {
        if reference.in_macro.is_some() {
            let key = (module.module.clone(), reference.macro_id);
            self.macro_unknowns.entry(key).or_default().push(reason);
        }
    }

    /// Each call of a macro of this crate is an edge to the module that defines it and to each
    /// module that its body names, also through the macros that its body calls. A name that two
    /// modules define, a call that the scan cannot place, and a body that it cannot read are
    /// UNKNOWN in the module of the call.
    pub(crate) fn macro_calls(&mut self, index: &Index<'_>, modules: &[Module]) {
        let mut defs = Defs::new();
        for module in modules {
            for def in &module.scan.macro_defs {
                let key = (module.crate_index, def.name.as_str());
                defs.entry(key).or_default().push((module, def));
            }
        }
        for module in modules {
            for call in &module.scan.macro_calls {
                self.expand(index, &defs, module, call);
                *self.ended_calls.entry(module.rel.clone()).or_default() += 1;
            }
        }
    }

    fn expand(&mut self, index: &Index<'_>, defs: &Defs<'_>, module: &Module, call: &MacroCall) {
        let name = call.name.as_str();
        let found = visible(defs, module, call, name);
        if found.is_empty() {
            return;
        }
        let reason = match (found.len(), call.placed) {
            (1, true) => None,
            (1, false) => Some(format!(
                "The macro {name}! is called where the scan cannot place it"
            )),
            _ => Some(format!(
                "The macro {name}! is defined more than once in the crate"
            )),
        };
        if let Some(reason) = reason {
            let evidence = self.cite(&module.rel, &call.site);
            self.gap(&reason, Some(&evidence), &module.module);
            return;
        }
        let mut seen = BTreeSet::new();
        let mut queue = vec![name.to_owned()];
        while let Some(next) = queue.pop() {
            if !seen.insert(next.clone()) {
                continue;
            }
            if let [(owner, def)] = visible(defs, module, call, &next)[..] {
                queue.extend(def.calls.iter().cloned());
                self.expand_methods(module, call, def);
                self.call_edge(index, module, owner, (&next, &call.site));
                self.unknown_expansion(module, call, (owner, def));
                self.expand_uses(index, module, call, (owner, def));
            }
        }
    }

    /// The methods that the body of a macro calls are calls of the module of the call (#953).
    fn expand_methods(&mut self, module: &Module, call: &MacroCall, def: &MacroDef) {
        for name in &def.members {
            let modules = self.macro_members.entry(name.clone()).or_default();
            modules.insert(module.module.clone());
        }
        let calls = def.methods.iter().map(|name| MethodCall {
            name: name.clone(),
            site: call.site.clone(),
            scope: Vec::new(),
            path: false,
            arity: None,
            on_self: None,
        });
        let found = self.macro_methods.entry(module.module.clone()).or_default();
        found.extend(calls);
    }

    /// The edges that the body of a macro names from the crate root, for the module of the call.
    fn expand_uses(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        call: &MacroCall,
        (owner, def): (&Module, &MacroDef),
    ) {
        let key = (owner.module.clone(), def.id);
        let uses = self.macro_uses.get(&key).cloned();
        for (edge, reference) in uses.into_iter().flatten() {
            let at = Reference {
                site: call.site.clone(),
                in_macro: None,
                ..reference
            };
            self.module_import(index, module, &at, &edge);
        }
    }

    /// The call is UNKNOWN for each reason why the scan cannot read the body of the macro.
    fn unknown_expansion(
        &mut self,
        module: &Module,
        call: &MacroCall,
        (owner, def): (&Module, &MacroDef),
    ) {
        let key = (owner.module.clone(), def.id);
        let found = self.macro_unknowns.get(&key).into_iter().flatten();
        let reasons: Vec<String> = def.unknowns.iter().chain(found).cloned().collect();
        for reason in reasons {
            let evidence = self.cite(&module.rel, &call.site);
            let reason = format!(
                "The macro {}! expands where the scan cannot read: {reason}",
                def.name
            );
            self.gap(&reason, Some(&evidence), &module.module);
        }
    }

    /// The call of `name!` depends on the module that defines the macro.
    fn call_edge(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        owner: &Module,
        (name, site): (&str, &Site),
    ) {
        let reference = Reference {
            root: name.to_owned(),
            path: format!("{name}!"),
            site: site.clone(),
            names: vec![name.to_owned()],
            ..Reference::default()
        };
        let edge = Edge {
            module: owner.module.clone(),
            lexical: owner.module.clone(),
            symbol: Some(name.to_owned()),
            level: 1,
            member_of: None,
        };
        self.module_import(index, module, &reference, &edge);
    }

    pub(crate) fn module_import(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        reference: &Reference,
        edge: &Edge,
    ) {
        let Some(target_rel) = index.rel(&edge.module) else {
            return;
        };
        if edge.module == module.module {
            self.ended += 1;
            return;
        }
        // The path of a macro body in its own definition is a template, not code (`macro_body`).
        let (template, form) = match reference.in_macro {
            Some(_) => ("template:", "macro_body"),
            None => ("", "module"),
        };
        let key = (
            module.module.clone(),
            format!("{template}module:{}", edge.module),
            reference.path.clone(),
        );
        if !self.seen.insert(key) {
            self.ended += 1;
            return;
        }
        let site = &reference.site;
        let identity = stable_id(
            "IMP",
            &[
                Part::Text(&module.module),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Text(form),
                Part::Text(&edge.module),
                Part::Text(&reference.path),
            ],
        );
        let evidence = self.cite(&module.rel, site);
        self.targets.push(Target::Local {
            import_id: FactId::new(identity.as_str()),
            module: ModuleName::new(edge.module.as_str()),
            file: target_rel.to_owned(),
            runtime_file: Some(target_rel.to_owned()),
            declaration_file: None,
        });
        let named = named(index, &mut self.publications, edge, &reference.via);
        let mut record = with_name(
            module_record(module, reference, edge, &identity, evidence),
            named,
        );
        record.data.data_mut().published_as = published(index, &module.module, reference);
        self.imports.push(record);
        self.ended += 1;
    }
}

/// What an import names (AD-604): the item, the type of a member, a glob (`*`) or a whole module
/// (`None`), with the publication route of the item.
pub(crate) struct ImportName {
    symbol: Option<String>,
    route: Route,
}

impl ImportName {
    /// A glob names every name of its module, and the scan does not know which one a use takes.
    pub(crate) fn glob() -> Self {
        ImportName {
            symbol: Some("*".to_owned()),
            route: Route::none(),
        }
    }
}

fn named(index: &Index<'_>, roots: &mut Publications, edge: &Edge, via: &Via) -> ImportName {
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

fn module_record(
    module: &Module,
    reference: &Reference,
    edge: &Edge,
    identity: &str,
    evidence: String,
) -> Record<ImportFact> {
    let (binding, reexport, block, glob) = match &reference.via {
        Via::Use {
            binding,
            reexport,
            block,
        } => (binding.clone(), *reexport, *block, false),
        Via::Glob { reexport, block } => (None, *reexport, *block, true),
        Via::Path | Via::Helper => (None, false, true, false),
    };
    let data = ImportData {
        source_module: ModuleName::new(&module.module),
        source_package: PackageName::new(package_of(&module.module)),
        target_module: ModuleName::new(&edge.module),
        target_package: PackageName::new(package_of(&edge.module)),
        symbol: if glob { None } else { edge.symbol.clone() },
        binding,
        specifier: Some(reference.path.clone()),
        relative_level: edge.level,
        reexport,
        module_level_import: !block,
        ..ImportData::statement()
    };
    let subjects = vec![module.module.clone(), edge.module.clone()];
    let at = (module.module.as_str(), reference.path.as_str());
    let fact = match (&reference.in_macro, reexport) {
        (Some(_), _) => ImportFact::MacroBody(data),
        (None, true) => ImportFact::Reexport(data),
        (None, false) => ImportFact::Import(data),
    };
    import_record((identity, evidence), at, subjects, fact)
}

/// The target of a path into another crate of the workspace: the deepest module that the path
/// names below the root of that crate. Without an index (a declared dependency) it is the root.
/// The name is the item after that module and its route (AD-604); a declared dependency names the
/// whole crate.
pub(crate) fn local_target(
    index: Option<&Index<'_>>,
    root: &Root,
    reference: &Reference,
    import_id: FactId,
) -> (Target, String, ImportName) {
    let rest = reference.names.get(1..).unwrap_or(&[]);
    let deepest = index.and_then(|index| {
        let Outcome::Edge(edge) = index.reach(&root.module, rest) else {
            return None;
        };
        let rel = index.rel(&edge.module)?.to_owned();
        let named = item(index, &edge.lexical, edge.symbol.as_deref());
        Some((edge.module, rel, named))
    });
    let whole = ImportName {
        symbol: None,
        route: Route::none(),
    };
    let (module, file, named) =
        deepest.unwrap_or_else(|| (root.module.clone(), root.rel.clone(), whole));
    let target = Target::Local {
        import_id,
        module: ModuleName::new(module.as_str()),
        file: file.clone(),
        runtime_file: Some(file),
        declaration_file: None,
    };
    (target, module, named)
}

#[cfg(test)]
#[path = "module_edges_tests.rs"]
mod tests;
