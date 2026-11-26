// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the repository outside the scan that can write a module of the scan (#1522,
//! AD-770). Such a write changes a route: `app.lib.f = secret` in a script makes
//! `from app.lib import f` give a private function.
//!
//! The walk reads the snapshot outside the scan modules. It does not enter `.git`, a symbolic
//! link, `__pycache__`, `node_modules`, a directory with a `CACHEDIR.TAG` (build output, AD-432) or
//! a `pyvenv.cfg` (installed packages). A test file (`is_test_source`) is not read: the stated
//! premise of the run covers test code, as it covers code outside the repository.
//!
//! - A Python file is read with the escape rule of AD-504 (`uses.rs`): a use of a module of the scan
//!   other than a load or call of an attribute escapes that module. A literal import call of a
//!   module of the scan escapes it and the packages above it.
//! - A hazard site of a Python file (AD-450) can give a module object by its name. Each module of
//!   the scan that a string of the file names then escapes (`outside_sites.rs`). Three forms are
//!   proven harmless: an import call whose name cannot name a module of the scan, `exec`, `eval` or
//!   `compile` of a literal text without a name, and a loader that makes a module under a foreign
//!   literal name (AD-1049).
//! - A Python file that Python cannot run (it does not decode or parse at Python 3.14) writes
//!   nothing. A file over the size limit, or with a declared encoding that is not UTF-8, can run:
//!   it is read as the text of an extension.
//! - An extension source (C, C++, Cython, a Rust file with the C API of Python) or a compiled
//!   module escapes each module of the scan that a dotted word of its text names
//!   (`outside_native.rs`).
//!
//! An escaped module withholds its routes and its names (AD-504, AD-550): the rules that read them
//! are UNKNOWN with the gap of the unproven publication route. A write that the repository does not
//! show (a name built at run time, code outside the repository) is the stated premise of the run.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::ids::ModuleName;
use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::vocab::ResolutionDimension;
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_snapshot::paths::join;
use archkeel_snapshot::{Entry, Snapshot};

use super::binders::Binders;
use super::class_writes::ClassWrites;
use super::hazards::Site;
use super::imports;
use super::lazy_cover::Sources;
use crate::discover::is_test_source;
use crate::module::{first_part, EvidenceMap, Module};
use crate::parse::parse;
use crate::source::{declared_encoding, decode, newlines};

#[path = "outside_grammar.rs"]
mod grammar;
#[path = "outside_native.rs"]
mod native;
#[path = "outside_sites.rs"]
mod sites;

/// The package of the names of the modules of the repository outside the scan. It is no Python
/// name, so it can be the name of no module of the scan.
const OUTSIDE: &str = "<outside>";

/// The directories that the walk does not enter by their name. Each file below a test directory
/// is a test source (`is_test_source`).
const SKIPPED: [&str; 6] = [
    ".git",
    "__pycache__",
    "node_modules",
    "test",
    "tests",
    "__tests__",
];

/// The files that prove a directory as build output or as installed packages.
const MARKERS: [&str; 2] = ["CACHEDIR.TAG", "pyvenv.cfg"];

/// The reason word of the gap that names a file outside the scan that withholds symbol records.
const WITHHELD: &str = "outside_file_withholds_symbols";

/// One site of a file outside the scan that gives a module object by its name. Each module that
/// the site names escapes, so the survey writes no symbol record for it (#1963).
pub(super) struct Withheld {
    file: String,
    line: Option<i64>,
    site: String,
    modules: Vec<String>,
}

/// The gap of each site that withholds symbol records. Its effect is `Symbols`: only a rule that
/// reads symbols is held, no edge, layout or cycle rule.
pub(super) fn gaps(withheld: &[Withheld]) -> Vec<Record<GapFact>> {
    // Two equal sites on one line give one reason and so one id; the facts allow each id once.
    // The sites of one place join, so no module drops out of the effect.
    let mut places: BTreeMap<(&str, Option<i64>, &str), BTreeSet<&str>> = BTreeMap::new();
    for found in withheld {
        let key = (found.file.as_str(), found.line, found.site.as_str());
        places
            .entry(key)
            .or_default()
            .extend(found.modules.iter().map(String::as_str));
    }
    places
        .into_iter()
        .map(|((file, line, site), modules)| {
            let count = BTreeSet::len(&modules);
            let unit = if count == 1 { "module" } else { "modules" };
            let at = line.map_or_else(|| file.to_owned(), |line| format!("{file}:{line}"));
            let reason = format!(
                "{WITHHELD}: {at} {site} names {count} {unit} of the scan; \
                 their symbol records are withheld"
            );
            let mut data = GapData::at(&reason, "");
            data.resolution_dimension = Some(ResolutionDimension::Imports);
            data.file = Some(file.to_owned());
            data.line = line;
            data.effect = Some(GapEffect::Symbols {
                modules: modules.into_iter().map(ModuleName::new).collect(),
            });
            let gap = GapFact::SourceResolutionGap(data);
            Record::unknown_gap(&reason, None, "", gap).1
        })
        .collect()
}

/// The files of the repository that the walk reads.
#[derive(Default)]
struct Files {
    python: Vec<String>,
    native: Vec<String>,
}

/// The modules of `scan` that code of the repository outside the scan can write.
pub(super) fn written(
    snapshot: &mut Snapshot,
    (scan, selected): (&mut Vec<Module>, &[String]),
    namespace: &str,
    writes: &mut ClassWrites,
) -> (HashSet<String>, Vec<Withheld>) {
    let names: HashSet<String> = scan.iter().map(|module| module.name.clone()).collect();
    let selected: HashSet<&str> = selected.iter().map(String::as_str).collect();
    let mut files = walk(snapshot, &selected);
    let roots = import_roots(scan);
    let paths = selected
        .iter()
        .copied()
        .chain(files.python.iter().chain(&files.native).map(String::as_str));
    paths.for_each(|rel| writes.add_path(&roots, rel));
    let mut outside = Vec::new();
    for rel in &files.python {
        match read(snapshot, rel, Vec::len(&outside)) {
            Read::Module(module) => outside.push(*module),
            Read::Silent => {}
            Read::Opaque => files.native.push(rel.clone()),
        }
    }
    let mut found = native::named(snapshot, &files.native, &names);
    // #1523: a store of an outside file can give a class of the scan a name (AD-802).
    for module in &outside {
        writes.add(&module.tree);
    }
    let binders: Vec<Binders> = outside
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let (literals, hazards) = super::hazards_split::split(&outside, &binders, (None, false), false);
    let mut withheld = Vec::new();
    for (index, range, target) in &literals {
        let hit = native::reached(target, &names);
        let module = &outside[*index];
        withheld.extend(site_of(
            module,
            "import call",
            module.location(range).line,
            &hit,
        ));
        found.extend(hit);
    }
    let mut own: HashMap<usize, Vec<&Site>> = HashMap::new();
    for (index, site) in &hazards {
        own.entry(*index).or_default().push(site);
    }
    let foreign: Vec<bool> = (0..Vec::len(&outside))
        .map(|at| {
            let sites = own.get(&at).map_or(&[][..], Vec::as_slice);
            sites::foreign_specs(&outside[at], sites.iter().copied(), &names)
        })
        .collect();
    // #1963, AD-1211: a file in the closed grammar of a read-only script holds nothing.
    let closed: Vec<bool> = outside.iter().map(grammar::closed).collect();
    for (index, site) in &hazards {
        if closed[*index] {
            continue;
        }
        let module = &outside[*index];
        let file = sites::File {
            module,
            foreign_specs: foreign[*index],
        };
        if !sites::harmless(site, &file, &names) {
            let hit = sites::named(module, &names);
            withheld.extend(site_of(
                module,
                &site.detail,
                module.location(&site.range).line,
                &hit,
            ));
            found.extend(hit);
        }
    }
    for (module, _) in outside.iter().zip(&closed).filter(|(_, closed)| !**closed) {
        for call in grammar::api_calls(module, &names) {
            let hit: Vec<String> = if call.computed {
                names.iter().cloned().collect()
            } else {
                sites::named(module, &names)
            };
            withheld.extend(site_of(module, &call.name, call.line, &hit));
            found.extend(hit);
        }
    }
    let (names_used, uses) = escaped(scan, outside, namespace);
    found.extend(names_used);
    withheld.extend(uses);
    (found, withheld)
}

/// The site of `module` that names `hit`, or `None` when it names no module of the scan.
fn site_of(module: &Module, site: &str, line: i64, hit: &[String]) -> Option<Withheld> {
    let modules: Vec<String> = hit
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    (!modules.is_empty()).then(|| Withheld {
        file: module.rel.clone(),
        line: Some(line),
        site: site.to_owned(),
        modules,
    })
}

/// The directories where the modules of the scan are found: the part of the path before the
/// first name of the module (`src` for the module `app.page` in the directory `src/app`).
fn import_roots(modules: &[Module]) -> HashSet<String> {
    let mut roots = HashSet::new();
    for module in modules {
        let path = String::as_str(&module.rel);
        let stem =
            str::strip_suffix(path, "/__init__.py").or_else(|| str::strip_suffix(path, ".py"));
        let tail = module.name.replace('.', "/");
        let Some(found) = stem.and_then(|stem| str::strip_suffix(stem, String::as_str(&tail)))
        else {
            continue;
        };
        if str::is_empty(found) || str::ends_with(found, '/') {
            roots.insert(str::trim_end_matches(found, '/').to_owned());
        }
    }
    roots
}

/// What the read of one Python file gives.
enum Read {
    /// A module to read.
    Module(Box<Module>),
    /// A file that Python cannot run.
    Silent,
    /// A file that Python can run and the collector cannot read.
    Opaque,
}

fn read(snapshot: &mut Snapshot, rel: &str, index: usize) -> Read {
    let Some(raw) = snapshot.read(rel) else {
        // A file that is absent or that does not read is a problem of the snapshot, so a gap.
        return if snapshot.size_gap(rel).is_some() {
            Read::Opaque
        } else {
            Read::Silent
        };
    };
    if declared_encoding(&raw).is_err() {
        return Read::Opaque;
    }
    let Some(text) = decode(&raw) else {
        return Read::Silent;
    };
    let text = newlines(text).into_owned();
    match parse(&text, PyMinor::Py314) {
        Ok(tree) => {
            let name = format!("{OUTSIDE}.f{index}");
            Read::Module(Box::new(Module::new(rel.to_owned(), name, text, tree)))
        }
        Err(_) => Read::Silent,
    }
}

/// The modules of the scan that the escape rule of AD-504 finds in `outside`. Only a file that
/// spells the first part of a module of the scan can bind one by an import.
fn escaped(
    scan: &mut Vec<Module>,
    files: Vec<Module>,
    namespace: &str,
) -> (HashSet<String>, Vec<Withheld>) {
    let parts: HashSet<String> = scan
        .iter()
        .map(|module| first_part(&module.name).to_owned())
        .collect();
    let count = Vec::len(scan);
    scan.extend(files.into_iter().filter(|module| {
        parts
            .iter()
            .any(|part| Module::text(module).contains(String::as_str(part)))
    }));
    if Vec::len(scan) == count {
        return (HashSet::new(), Vec::new());
    }
    let binders: Vec<Binders> = scan
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let none = HashSet::new();
    let mut sources = Sources::new();
    let mut evidence = EvidenceMap::new();
    let context = (&none, &sources);
    let records = imports::collect_all(scan, &binders, namespace, &mut evidence, context, &[]);
    // The uses of an outside file follow its names through the records of the scan, so both
    // walks read all records; the escapes that the scan alone gives are not its own.
    let all = super::uses::settled(scan, &records.records, &mut sources.clone());
    let from = |record: &Record<ImportFact>| {
        ModuleName::as_str(&ImportFact::data(&record.data).source_module).to_owned()
    };
    let own: Vec<_> = (records.records.iter())
        .filter(|record| !outside(&from(record)))
        .cloned()
        .collect();
    let outsiders = scan.split_off(count);
    let fresh = sources.clone();
    let inside = super::uses::settled(scan, &own, &mut sources);
    let names: HashSet<&str> = scan
        .iter()
        .map(|module| String::as_str(&module.name))
        .collect();
    let result: HashSet<String> = (all.into_iter())
        .filter(|name| names.contains(String::as_str(name)) && !inside.contains(name))
        .collect();
    // #1963: the file of each use. One file names every module that escapes. With more files the
    // scan runs once more for each file, with that file alone added, until each module has a file.
    let mut uses = Vec::new();
    let mut open: BTreeSet<&String> = result.iter().collect();
    let single = Vec::len(&outsiders) == 1;
    for module in outsiders {
        if open.is_empty() {
            break;
        }
        let (hit, module): (HashSet<String>, Module) = if single {
            (result.clone(), module)
        } else {
            let mine = (records.records.iter())
                .filter(|record| from(record) == module.name)
                .cloned();
            let both: Vec<_> = own.iter().cloned().chain(mine).collect();
            let name = module.name.clone();
            scan.push(module);
            let hit = super::uses::settled(scan, &both, &mut fresh.clone());
            let Some(module) = scan.pop() else { break };
            debug_assert_eq!(module.name, name);
            (hit, module)
        };
        let modules: Vec<String> = (hit.into_iter())
            .filter(|name| result.contains(name) && !inside.contains(name))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        open.retain(|name| !modules.contains(*name));
        if !modules.is_empty() {
            let file = module.rel.clone();
            uses.push(Withheld {
                file,
                line: None,
                site: "use of a module".to_owned(),
                modules,
            });
        }
    }
    (result, uses)
}

/// True for the name of a module of the repository outside the scan.
fn outside(name: &str) -> bool {
    name.starts_with(OUTSIDE)
}

/// The Python files and the extension files of the snapshot outside the scan modules.
fn walk(snapshot: &mut Snapshot, selected: &HashSet<&str>) -> Files {
    let mut files = Files::default();
    let mut pending = vec![String::new()];
    while let Some(directory) = pending.pop() {
        let Some(entries) = snapshot.listing(if String::is_empty(&directory) {
            "."
        } else {
            &directory
        }) else {
            continue;
        };
        let names: HashMap<&str, Entry> = entries
            .iter()
            .map(|(n, e)| (String::as_str(n), *e))
            .collect();
        if MARKERS
            .iter()
            .any(|marker| names.get(marker) == Some(&Entry::File))
        {
            continue;
        }
        for (name, entry) in &entries {
            let rel = join(&directory, name);
            match entry {
                Entry::Directory if !SKIPPED.contains(&String::as_str(name)) => pending.push(rel),
                Entry::File
                    if !selected.contains(String::as_str(&rel)) && !is_test_source(&rel) =>
                {
                    files.add(rel);
                }
                _ => {}
            }
        }
    }
    files.python.sort();
    files.native.sort();
    files
}

impl Files {
    fn add(&mut self, rel: String) {
        if rel.ends_with(".py") || rel.ends_with(".pyw") {
            self.python.push(rel);
        } else if native::extension(&rel) {
            self.native.push(rel);
        }
    }
}

#[cfg(test)]
#[path = "outside_tests.rs"]
mod tests;
