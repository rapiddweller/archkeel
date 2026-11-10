// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of the edges between the modules of one crate: one `import` or `reexport` record
//! for each distinct path of a module that names another module of its crate, and one gap for
//! each path that the scan cannot resolve. The resolution is in `modules.rs`.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::data::ImportData;
use archkeel_facts::ids::{ModuleName, PackageName};
use archkeel_facts::{ImportFact, Record};
use archkeel_wire::identity::{package_of, stable_id, Part};
use archkeel_wire::reply::Target;

use crate::builder::{import_record, Builder};
use crate::crates::Root;
use crate::modules::{Edge, Index, Outcome};
use crate::scan::{Reference, Site, Via};
use crate::tree::Module;

/// The `macro_rules!` definitions of each crate, by name: the module, and the macros it calls.
type Defs<'a> = BTreeMap<(usize, &'a str), Vec<(&'a Module, &'a BTreeSet<String>)>>;

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
        match index.resolve(frame, reference) {
            Outcome::None => {}
            Outcome::Unknown(reason) => {
                let evidence = self.cite(&module.rel, &reference.site);
                self.gap(&reason, Some(&evidence), &module.module);
            }
            Outcome::Edge(edge) => match &reference.in_macro {
                None => self.module_import(index, module, reference, &edge),
                Some(name) => self.macro_use(index, module, reference, edge, name),
            },
        }
    }

    /// A path in a `macro_rules!` body that starts at `crate` names the same module wherever the
    /// macro expands, so each call of the macro gets the edge (`macro_calls`). Any other path in a
    /// body is relative to the place of the call, and the scan does not know it.
    fn macro_use(
        &mut self,
        index: &Index<'_>,
        module: &Module,
        reference: &Reference,
        edge: Edge,
        name: &str,
    ) {
        if reference.names.first().map(String::as_str) == Some("crate") {
            // The file of the definition writes the path too.
            self.module_import(index, module, reference, &edge);
            let key = (module.crate_index, name.to_owned());
            self.macro_uses
                .entry(key)
                .or_default()
                .push((edge, reference.clone()));
            return;
        }
        let evidence = self.cite(&module.rel, &reference.site);
        let reason =
            "A macro_rules! body holds a module path that is relative to the place of the call";
        self.gap(reason, Some(&evidence), &module.module);
    }

    /// Each call of a macro of this crate is an edge to the module that defines it and to each
    /// module that its body names, also through the macros that its body calls. A name that two
    /// modules define is UNKNOWN.
    pub(crate) fn macro_calls(&mut self, index: &Index<'_>, modules: &[Module]) {
        let mut defs = Defs::new();
        for module in modules {
            for def in &module.scan.macro_defs {
                let key = (module.crate_index, def.name.as_str());
                defs.entry(key).or_default().push((module, &def.calls));
            }
        }
        for module in modules {
            for (name, site) in &module.scan.macro_calls {
                self.expand(index, &defs, (module, name), site);
            }
        }
    }

    fn expand(
        &mut self,
        index: &Index<'_>,
        defs: &Defs<'_>,
        (module, name): (&Module, &str),
        site: &Site,
    ) {
        let Some(found) = defs.get(&(module.crate_index, name)) else {
            return;
        };
        if found.len() > 1 {
            let evidence = self.cite(&module.rel, site);
            let reason = format!("The macro {name}! is defined more than once in the crate");
            self.gap(&reason, Some(&evidence), &module.module);
            return;
        }
        let mut seen = BTreeSet::new();
        let mut queue = vec![name.to_owned()];
        while let Some(next) = queue.pop() {
            if !seen.insert(next.clone()) {
                continue;
            }
            let owner = defs.get(&(module.crate_index, next.as_str()));
            if let Some([(owner, calls)]) = owner.map(Vec::as_slice) {
                queue.extend(calls.iter().cloned());
                self.call_edge(index, module, owner, (&next, site));
            }
            let uses = self.macro_uses.get(&(module.crate_index, next)).cloned();
            for (edge, reference) in uses.into_iter().flatten() {
                let at = Reference {
                    site: site.clone(),
                    ..reference
                };
                self.module_import(index, module, &at, &edge);
            }
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
        };
        self.module_import(index, module, &reference, &edge);
    }

    fn module_import(
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
            return;
        }
        let key = (
            module.module.clone(),
            format!("module:{}", edge.module),
            reference.path.clone(),
        );
        if !self.seen.insert(key) {
            return;
        }
        let site = &reference.site;
        let identity = stable_id(
            "IMP",
            &[
                Part::Text(&module.module),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Text("module"),
                Part::Text(&edge.module),
                Part::Text(&reference.path),
            ],
        );
        let evidence = self.cite(&module.rel, site);
        self.targets.push(Target::Local {
            import_id: identity.clone(),
            module: edge.module.clone(),
            file: target_rel.to_owned(),
            runtime_file: Some(target_rel.to_owned()),
            declaration_file: None,
        });
        self.imports
            .push(module_record(module, reference, edge, &identity, evidence));
    }
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
        Via::Path => (None, false, true, false),
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
    let fact = if reexport {
        ImportFact::Reexport(data)
    } else {
        ImportFact::Import(data)
    };
    import_record((identity, evidence), at, subjects, fact)
}

/// The target of a path into another crate of the workspace: the deepest module that the path
/// names below the root of that crate. Without an index (a declared dependency) it is the root.
pub(crate) fn local_target(
    index: Option<&Index<'_>>,
    root: &Root,
    reference: &Reference,
    import_id: String,
) -> (Target, String) {
    let rest = reference.names.get(1..).unwrap_or(&[]);
    let deepest = index.and_then(|index| {
        let module = index.deepest(&root.module, rest);
        index.rel(&module).map(|rel| (module, rel.to_owned()))
    });
    let (module, file) = deepest.unwrap_or_else(|| (root.module.clone(), root.rel.clone()));
    let target = Target::Local {
        import_id,
        module: module.clone(),
        file: file.clone(),
        runtime_file: Some(file),
        declaration_file: None,
    };
    (target, module)
}

#[cfg(test)]
#[path = "module_edges_tests.rs"]
mod tests;
