// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The imports of a reply, split as the reference engine splits them (slice S2).
//!
//! Reference engine: `check/evaluation/imports.py` `split_imports` (an unresolved import and a
//! macro body leave the imports), `check/evaluation/evaluate.py` `evaluate_source` (the external
//! package and the builtin mark of a resolved import) and `ir/import_gaps.py`
//! `derived_unresolved_imports` (an unresolved import whose site no collector gap names).
//!
//! The store accepts a reply only when each import has exactly one typed target, so each
//! import record has its target here.
//!
//! A macro body is not an import of the edges, the cycles or the ranks (AD-349). It stays as a
//! row of its own (`MacroBody`): the fan counts of the modules read it (`count_macro_bodies`).

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::GapEffect;
use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::profile_traits::TargetMarks;
use archkeel_facts::vocab::ResolutionDimension;
use archkeel_facts::Record;
use archkeel_facts::{ImportFact, Section};

/// What the typed target of a resolved import is.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Resolved {
    /// A module of the scanned tree.
    Local,
    /// An external package: its name.
    External(String),
    /// A part of the platform of the language.
    Builtin,
}

/// What a record states about publication: the route of its name (AD-504, AD-604), the name
/// that it publishes outside the package of its module (AD-608), and whether it receives a
/// publication of another crate of the workspace (AD-622).
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Published {
    pub(crate) chain: Vec<String>,
    pub(crate) complete: bool,
    pub(crate) outside: Option<String>,
    pub(crate) other_crate: bool,
}

/// One resolved import that is not a macro body: the input of the edges and the rules.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Import {
    pub(crate) id: String,
    pub(crate) source_module: String,
    pub(crate) target_module: String,
    pub(crate) source_package: String,
    pub(crate) target_package: String,
    pub(crate) under_type_checking: bool,
    pub(crate) symbol: Option<String>,
    pub(crate) symbols_known: bool,
    pub(crate) call_form: bool,
    pub(crate) published: Published,
    pub(crate) relative: bool,
    pub(crate) resolved: Resolved,
    pub(crate) evidence: Vec<String>,
    pub(crate) call_by_name: bool,
    pub(crate) unbound_type: bool,
}

impl Import {
    /// The id of the import record.
    pub fn id(&self) -> &str {
        &self.id
    }

    /// The module that imports.
    pub fn source_module(&self) -> &str {
        &self.source_module
    }

    /// The module that the import names.
    pub fn target_module(&self) -> &str {
        &self.target_module
    }

    /// The package of the source module.
    pub fn source_package(&self) -> &str {
        &self.source_package
    }

    /// The package of the target module.
    pub fn target_package(&self) -> &str {
        &self.target_package
    }

    /// True when only a type check reads the import.
    pub fn under_type_checking(&self) -> bool {
        self.under_type_checking
    }

    /// True for a relative import: it resolves inside the scanned tree.
    /// The imported name, or `None` for a whole-module import.
    pub fn symbol(&self) -> Option<&str> {
        self.symbol.as_deref()
    }

    /// True when the collector knows each name that the import uses.
    /// A call-form import is a call, not a statement (`importlib.import_module("m")`, `import("m")`):
    /// it may run, or not, and it proves no use of a name of the target (AD-514, AD-536).
    pub fn call_form(&self) -> bool {
        self.call_form
    }

    /// True for a call-form import whose module the collector read as a name, with no specifier
    /// string of the source (`importlib.import_module("m")`). Release 4.0.1 reads only the import
    /// statements of that collector, so its UML target compare does not count this call. A call
    /// with a specifier (`import("./m")`) is a counted import there (AD-536).
    pub fn call_by_name(&self) -> bool {
        self.call_by_name
    }

    /// True for an import in type position with no bound name (`import("m").T`, `typeof
    /// import("m")`): it proves no use of a name of the target, like a call (AD-514, AD-536).
    pub fn unbound_type(&self) -> bool {
        self.unbound_type
    }

    /// True when the collector read the imported names, so a use of a name can be judged.
    pub fn symbols_known(&self) -> bool {
        self.symbols_known
    }

    /// The publication names whose route the collector records.
    pub fn reexport_chain(&self) -> &[String] {
        &self.published.chain
    }

    /// False when the collector proves only the first hops of the route: a later hop may follow,
    /// so a route with no public hop proves no violation (AD-604).
    pub fn route_complete(&self) -> bool {
        self.published.complete
    }

    /// The name that the record publishes outside the package of its module, when it is a
    /// re-export that does (`*` for a glob; AD-608).
    pub fn published_as(&self) -> Option<&str> {
        self.published.outside.as_deref()
    }

    /// True when the record names a module of another crate of the workspace by that crate's
    /// name, as a binary target names its library (AD-622).
    pub fn other_crate(&self) -> bool {
        self.published.other_crate
    }

    /// True for a relative import, which names its target by position and not by name.
    pub fn relative(&self) -> bool {
        self.relative
    }

    /// The typed target.
    pub fn resolved(&self) -> &Resolved {
        &self.resolved
    }

    /// The evidence ids of the import record, sorted.
    pub fn evidence(&self) -> &[String] {
        &self.evidence
    }
}

/// The source and target module of a resolved macro body (`split_imports` templates).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct MacroBody {
    pub(crate) source_module: String,
    pub(crate) target_module: String,
}

impl MacroBody {
    /// The module that holds the macro body.
    pub(crate) fn source_module(&self) -> &str {
        &self.source_module
    }

    /// The module that the macro body names.
    pub(crate) fn target_module(&self) -> &str {
        &self.target_module
    }
}

/// The imports of a reply, split.
#[derive(Debug, Default)]
pub(crate) struct Split {
    /// The resolved imports that are not macro bodies, in the order of the reply.
    pub(crate) imports: Vec<Import>,
    /// The resolved macro bodies, in the order of the reply.
    pub(crate) macro_bodies: Vec<MacroBody>,
    /// The number of unresolved imports that no collector gap names (each is a coverage
    /// failure of the reference engine).
    pub(crate) unknown: usize,
}

/// A gap of the import resolution: its id, the module and the evidence that it names, and its
/// effect.
struct Site<'f> {
    id: &'f str,
    module: Option<&'f str>,
    evidence: Vec<&'f str>,
    effect: Option<&'f GapEffect>,
}

impl Site<'_> {
    /// True when the gap names the unresolved import of `source` at `cited` and its effect leaves
    /// the code of `source` unknown (AD-564): the same site, or a citation of each evidence of
    /// the import. An unresolved import can bind or re-export a name, so an effect on the edges
    /// alone does not cover it. A gap without an effect names an import only by the same site
    /// (`named` in `split`).
    fn covers(&self, source: &str, cited: &[&str]) -> bool {
        let Some(effect) = self.effect else {
            return false;
        };
        let names = (self.module == Some(source) && self.evidence == cited)
            || (!cited.is_empty() && cited.iter().all(|id| self.evidence.contains(id)));
        let code = match effect {
            GapEffect::EveryModule => true,
            GapEffect::Modules { modules } => {
                modules.iter().any(|module| module.as_str() == source)
            }
            GapEffect::Edges { .. } | GapEffect::Layout { .. } => false,
        };
        names && code
    }
}

/// Split the imports of a reply. An unresolved import leaves first, then a macro body, as
/// `split_imports` checks them.
pub(crate) fn split(facts: &Facts, declared: impl Fn(&str) -> bool) -> Split {
    let targets: HashMap<&str, &Target> = facts
        .imports
        .iter()
        .map(|target| (target.import_id().as_str(), target))
        .collect();
    let mut sites = resolution_sites(facts);
    sites.retain(|site| !declared(site.id));
    let named: HashSet<(Option<&str>, Vec<&str>)> = sites
        .iter()
        .filter(|site| site.effect.is_none())
        .map(|site| (site.module, site.evidence.clone()))
        .collect();
    // A profile without marks reads every resolved target by its module (AD-450).
    let typed = facts.profile.target_marks() == TargetMarks::Typed;
    let mut found = Split::default();
    for record in facts.sections.iter().flat_map(records) {
        let data = record.data.data();
        let resolved = match targets.get(record.id.as_str()) {
            Some(Target::Unresolved { .. }) => {
                let source = data.source_module.as_str();
                let site = (Some(source), evidence(record));
                let covered = sites.iter().any(|gap| gap.covers(source, &site.1));
                found.unknown += usize::from(!named.contains(&site) && !covered);
                continue;
            }
            _ if matches!(record.data, ImportFact::MacroBody(_)) => {
                found.macro_bodies.push(MacroBody {
                    source_module: data.source_module.as_str().to_owned(),
                    target_module: data.target_module.as_str().to_owned(),
                });
                continue;
            }
            Some(Target::External { package, .. }) if typed => {
                Resolved::External(package.as_str().into())
            }
            Some(Target::Builtin { .. }) if typed => Resolved::Builtin,
            Some(Target::External { .. } | Target::Builtin { .. }) => Resolved::Local,
            Some(Target::Local { .. }) | None => Resolved::Local,
        };
        found.imports.push(Import {
            id: record.id.as_str().to_owned(),
            source_module: data.source_module.as_str().to_owned(),
            target_module: data.target_module.as_str().to_owned(),
            source_package: data.source_package.as_str().to_owned(),
            target_package: data.target_package.as_str().to_owned(),
            under_type_checking: data.under_type_checking,
            symbol: data.symbol.clone(),
            symbols_known: data.symbols_known,
            call_form: matches!(record.data, ImportFact::DynamicImport(_)),
            call_by_name: matches!(record.data, ImportFact::DynamicImport(_))
                && data.specifier.is_none(),
            unbound_type: matches!(record.data, ImportFact::ImportType(_))
                && data.binding.is_none(),
            published: Published {
                chain: data.reexport_chain.clone().unwrap_or_default(),
                complete: data.route_complete != Some(false),
                outside: data.published_as.clone(),
                other_crate: data.other_crate == Some(true),
            },
            relative: data.relative_level != 0,
            resolved,
            evidence: sorted(evidence(record)),
        });
    }
    found
}

/// The gaps of the import resolution, in the order of the reply.
fn resolution_sites(facts: &Facts) -> Vec<Site<'_>> {
    facts
        .coverage
        .gaps
        .iter()
        .filter_map(|gap| {
            let data = crate::coverage::data_of(&gap.data);
            (data.resolution_dimension == Some(ResolutionDimension::Imports)).then(|| Site {
                id: gap.id.as_str(),
                module: data.module.as_ref().map(|m| m.as_str()),
                evidence: evidence(gap),
                effect: data.effect.as_ref(),
            })
        })
        .collect()
}

/// The number of unresolved imports that each gap covers (AD-664): a declared reach cannot
/// narrow such a gap, because it does not resolve the imports.
pub(crate) fn covered(facts: &Facts) -> HashMap<&str, usize> {
    let targets: HashSet<&str> = facts
        .imports
        .iter()
        .filter(|target| matches!(target, Target::Unresolved { .. }))
        .map(|target| target.import_id().as_str())
        .collect();
    let sites = resolution_sites(facts);
    let mut found = HashMap::new();
    for record in facts.sections.iter().flat_map(records) {
        if !targets.contains(record.id.as_str()) {
            continue;
        }
        let source = record.data.data().source_module.as_str();
        let cited = evidence(record);
        for site in sites.iter().filter(|site| site.covers(source, &cited)) {
            *found.entry(site.id).or_default() += 1;
        }
    }
    found
}

fn records(section: &Section) -> &[Record<ImportFact>] {
    match section {
        Section::Imports(records) => records,
        _ => &[],
    }
}

/// The evidence ids sorted, as `classified` sorts the `evidence_ids` of a row. The site of a
/// gap keeps the order of the reply, as `derived_unresolved_imports` compares it.
fn sorted(mut ids: Vec<&str>) -> Vec<String> {
    ids.sort_unstable();
    ids.into_iter().map(str::to_owned).collect()
}

fn evidence<D>(record: &Record<D>) -> Vec<&str> {
    record.evidence_ids.iter().map(|id| id.as_str()).collect()
}

#[cfg(test)]
#[path = "imports_effect_tests.rs"]
mod effect_tests;
