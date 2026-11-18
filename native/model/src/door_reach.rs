// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declared reach of door sites (AD-664).
//!
//! A door gap (`GapData.door`) states `every_module`: the door can run code that the scan does
//! not see (AD-564). A contract can name one door site and the module prefixes that the door may
//! load (`loads`) or change (`changes`). This file matches each declaration of the root contract
//! to the doors of the reply, one time, while the graph is derived:
//!
//! - A declaration that matches exactly one door, with a valid reach, is applied. The gap keeps
//!   only what the premise leaves unknown: the code of each module of the scan below a
//!   `changes` prefix. The door writes a declared import from its module to each module of the
//!   scan below a `loads` prefix, or to the outside package of the prefix, so the edge rules read
//!   these edges as real edges.
//! - Each other declaration is a problem (no door, more than one door, a door with two
//!   declarations, a word that names no form, a reach outside the scan). A problem is never
//!   applied: its door keeps `every_module`, and the core reports the problem.
//!
//! This file matches collector site metadata. It does not read source code.

use std::collections::{BTreeMap, HashMap};

use archkeel_contract::DoorReach as Declaration;
use archkeel_facts::data::{DoorForm, GapEffect};
use archkeel_facts::envelope::{Facts, FileFact};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::ModuleName;

use crate::coverage::data_of;
use crate::gap_class::EffectGap;
use crate::imports::{Import, Published, Resolved};
use crate::ownership::in_scope;
use crate::settings::Settings;

/// One applied declaration: the door site, the gap and the reach.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Applied {
    /// The id of the declaration.
    pub id: String,
    /// The id of the gap of the door.
    pub gap: String,
    /// The module of the door.
    pub module: String,
    /// The form of the door.
    pub form: DoorForm,
    /// The line of the door site.
    pub line: u32,
    /// The declared module prefixes that the door may import.
    pub loads: Vec<String>,
    /// The source binding and template of a constant-bound declaration.
    pub constant: Option<String>,
    /// The scanned targets of the possible dependency edges supplied by the declaration.
    pub possible_loads: Vec<String>,
    /// The declared module prefixes whose names the door may change.
    pub changes: Vec<String>,
    /// What the gap still leaves unknown under the premise, or `None` for nothing.
    pub(crate) effect: Option<GapEffect>,
    /// The effect that the collector stated for the door.
    pub(crate) stated: GapEffect,
}

impl Applied {
    /// `D-1 (pkg.mod:12 eval)`: the declaration and its site, for a reader.
    pub fn site(&self) -> String {
        let site = format!(
            "{} ({}:{} {})",
            self.id,
            self.module,
            self.line,
            self.door()
        );
        match &self.constant {
            Some(bound) => format!("{site}: loads only the targets from {bound}"),
            None => site,
        }
    }

    /// The word of the form of the door.
    pub fn door(&self) -> &'static str {
        self.form.word()
    }
}

/// Why one declaration is not applied.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DoorProblem {
    /// No door of the reply has this site: it moved, changed its form or is gone.
    Unmatched,
    /// More than one door has this site: their number.
    Ambiguous(usize),
    /// The door has more than one declaration: the ids of the others.
    Repeated(Vec<String>),
    /// The word names no form of a door.
    Form,
    /// A `changes` prefix holds no module of the scan: a change outside the scan can change
    /// any import.
    ChangesOutside(String),
    /// A `loads` prefix lies in a top package of the scan and holds no module of it.
    LoadsNothing(String),
    /// The site binds the door to a name that these modules import: the door leaves its module.
    Exported(Vec<String>),
    /// The gap of the door covers this number of imports that the scan cannot resolve.
    Unresolved(usize),
    /// The scanned evidence does not establish a usable constant bound.
    Constant(String),
}

impl DoorProblem {
    /// The stable code of the problem, for its row.
    pub fn code(&self) -> &'static str {
        match self {
            DoorProblem::Unmatched => "door_reach.unmatched",
            DoorProblem::Ambiguous(_) => "door_reach.ambiguous",
            DoorProblem::Repeated(_) => "door_reach.repeated",
            DoorProblem::Form
            | DoorProblem::ChangesOutside(_)
            | DoorProblem::LoadsNothing(_)
            | DoorProblem::Exported(_)
            | DoorProblem::Constant(_)
            | DoorProblem::Unresolved(_) => "door_reach.invalid",
        }
    }

    /// What the problem is, for a reader.
    pub fn text(&self) -> String {
        match self {
            DoorProblem::Unmatched => "matches no door of the scan: the door moved, changed its \
                                   form or is gone; the declaration is not applied"
                .to_owned(),
            DoorProblem::Ambiguous(count) => format!(
                "matches {count} doors; name the site by its line; the declaration is not applied"
            ),
            DoorProblem::Repeated(others) => format!(
                "names a door that {} also name; the declarations of the door are not applied",
                others.join(", ")
            ),
            DoorProblem::Form => format!(
                "names no form of a door; the forms are {}; the declaration is not applied",
                DoorForm::ALL.map(DoorForm::word).join(", ")
            ),
            DoorProblem::ChangesOutside(prefix) => format!(
                "changes {prefix}, which holds no module of the scan; a change outside the \
                 scan can change any import; the declaration is not applied"
            ),
            DoorProblem::Exported(importers) => format!(
                "binds the door to a name that {} import, so the door runs outside its module; \
                 the declaration is not applied",
                importers.join(", ")
            ),
            DoorProblem::Unresolved(count) => format!(
                "names a door whose gap covers {count} imports that the scan cannot resolve; a \
                 declared reach does not resolve them; the declaration is not applied"
            ),
            DoorProblem::LoadsNothing(prefix) => format!(
                "loads {prefix}, which lies in the project and holds no module of the scan; the \
                 declaration is not applied"
            ),
            DoorProblem::Constant(reason) => format!("{reason}; the declaration is not applied"),
        }
    }
}

/// The declarations of a run, matched to the doors of its reply.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Doors {
    applied: Vec<Applied>,
    problems: Vec<(usize, String, DoorProblem)>,
    imports: Vec<Import>,
}

impl Doors {
    /// Each applied declaration, in contract order.
    pub fn applied(&self) -> &[Applied] {
        &self.applied
    }

    /// Each declaration that is not applied: its index in the contract, its id and the problem.
    pub fn problems(&self) -> &[(usize, String, DoorProblem)] {
        &self.problems
    }

    /// The declared imports of the applied declarations.
    pub(crate) fn take_imports(&mut self) -> Vec<Import> {
        std::mem::take(&mut self.imports)
    }

    /// The applied declaration of the gap `id`, if any.
    pub(crate) fn of_gap(&self, id: &str) -> Option<&Applied> {
        self.applied.iter().find(|applied| applied.gap == id)
    }
}

/// The gaps with an effect under the applied declarations: a declared gap keeps what its premise
/// leaves unknown, and leaves the list when that is nothing.
pub(crate) fn narrowed(doors: &Doors, gaps: Vec<EffectGap>) -> Vec<EffectGap> {
    gaps.into_iter()
        .filter_map(|gap| match doors.of_gap(&gap.id) {
            None => Some(gap),
            Some(applied) => applied
                .effect
                .clone()
                .map(|effect| EffectGap { id: gap.id, effect }),
        })
        .collect()
}

/// One door of the reply.
struct Door<'f> {
    gap: &'f str,
    module: &'f str,
    form: DoorForm,
    line: u32,
    scope: Option<&'f str>,
    effect: &'f GapEffect,
    evidence: Vec<String>,
    binding: Option<&'f str>,
}

/// Match the declarations to the doors of `facts`.
pub(crate) fn matched(declared: &[Declaration], facts: &Facts, settings: &Settings) -> Doors {
    let doors: Vec<Door<'_>> = facts.coverage.gaps.iter().filter_map(door).collect();
    let mut found = Doors::default();
    let mut by_gap: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
    let mut matches: Vec<(usize, &Door<'_>)> = Vec::new();
    for (index, declaration) in declared.iter().enumerate() {
        let problem = |found: &mut Doors, problem| {
            let id = declaration.id().as_text().to_owned();
            found.problems.push((index, id, problem));
        };
        let Some(form) = DoorForm::of_word(declaration.door()) else {
            problem(&mut found, DoorProblem::Form);
            continue;
        };
        let sites: Vec<&Door<'_>> = doors
            .iter()
            .filter(|door| at(door, declaration, form))
            .collect();
        match sites.as_slice() {
            [] => problem(&mut found, DoorProblem::Unmatched),
            [door] => {
                by_gap.entry(door.gap).or_default().push(index);
                matches.push((index, door));
            }
            many => problem(&mut found, DoorProblem::Ambiguous(many.len())),
        }
    }
    let unresolved = crate::imports::covered(facts);
    let files: HashMap<&str, &FileFact> = facts
        .files
        .iter()
        .map(|file| (file.module.as_str(), file))
        .collect();
    for (index, door) in matches {
        let declaration = &declared[index];
        let id = declaration.id().as_text().to_owned();
        let shared = &by_gap[door.gap];
        if shared.len() > 1 {
            let others = shared.iter().filter(|other| **other != index);
            let others = others.map(|other| declared[*other].id().as_text().to_owned());
            found
                .problems
                .push((index, id, DoorProblem::Repeated(others.collect())));
            continue;
        }
        if let Some(count) = unresolved.get(door.gap) {
            found
                .problems
                .push((index, id, DoorProblem::Unresolved(*count)));
            continue;
        }
        let importers = importers(facts, door);
        if !importers.is_empty() {
            found
                .problems
                .push((index, id, DoorProblem::Exported(importers)));
            continue;
        }
        match apply(declaration, door, &files, settings) {
            Ok((applied, imports)) => {
                found.applied.push(applied);
                found.imports.extend(imports);
            }
            Err(problem) => found.problems.push((index, id, problem)),
        }
    }
    found.problems.sort_by_key(|(index, _, _)| *index);
    found.imports.sort_by(|a, b| a.id.cmp(&b.id));
    found.imports.dedup_by(|a, b| a.id == b.id);
    found
}

/// The door of a gap, when the collector marks one and names its module and its effect.
fn door(gap: &archkeel_facts::Record<archkeel_facts::GapFact>) -> Option<Door<'_>> {
    let data = data_of(&gap.data);
    let site = data.door.as_ref()?;
    Some(Door {
        gap: gap.id.as_str(),
        module: data.module.as_ref()?.as_str(),
        form: site.form,
        line: site.line,
        scope: (!site.line_only).then(|| site.scope.as_deref().unwrap_or("")),
        effect: data.effect.as_ref()?,
        evidence: gap
            .evidence_ids
            .iter()
            .map(|id| id.as_str().to_owned())
            .collect(),
        binding: site.binding.as_deref(),
    })
}

/// The modules that import the name that the door site binds, or all names of its module, sorted
/// and distinct.
fn importers(facts: &Facts, door: &Door<'_>) -> Vec<String> {
    let Some(binding) = door.binding else {
        return Vec::new();
    };
    let mut found: Vec<String> = facts
        .sections
        .iter()
        .flat_map(|section| match section {
            archkeel_facts::Section::Imports(records) => records.as_slice(),
            _ => &[],
        })
        .map(|record| record.data.data())
        .filter(|data| {
            data.source_module.as_str() != door.module
                && data.target_module.as_str() == door.module
                && matches!(data.symbol.as_deref(), Some(name) if name == binding || name == "*")
        })
        .map(|data| data.source_module.as_str().to_owned())
        .collect();
    found.sort_unstable();
    found.dedup();
    found
}

/// True when the declaration names this door: the module, the form, and the line and the scope
/// that it names.
fn at(door: &Door<'_>, declaration: &Declaration, form: DoorForm) -> bool {
    door.module == declaration.module().as_text()
        && door.form == form
        && declaration
            .line()
            .is_none_or(|line| u64::from(door.line) == line)
        && declaration
            .scope()
            .as_deref()
            .is_none_or(|scope| door.scope == Some(scope))
}

/// The applied declaration and its declared imports, or the problem of its reach.
fn apply(
    declaration: &Declaration,
    door: &Door<'_>,
    files: &HashMap<&str, &FileFact>,
    settings: &Settings,
) -> Result<(Applied, Vec<Import>), DoorProblem> {
    let below = |prefix: &str| -> Vec<&str> {
        let mut names: Vec<&str> = files
            .keys()
            .copied()
            .filter(|module| in_scope(module, prefix))
            .collect();
        names.sort_unstable();
        names
    };
    let mut changed = Vec::new();
    for prefix in declaration.changes() {
        let names = below(prefix.as_text());
        if names.is_empty() {
            return Err(DoorProblem::ChangesOutside(prefix.as_text().to_owned()));
        }
        changed.extend(names.into_iter().map(ModuleName::new));
    }
    changed.sort_by(|a, b| a.as_str().cmp(b.as_str()));
    changed.dedup();
    let source = files
        .get(door.module)
        .map_or("", |file| file.package.as_str());
    let bound = declaration.loads_from().as_ref().map(|bound| {
        (
            bound.constant().as_str(),
            bound.template().as_str(),
            bound.call().as_str(),
        )
    });
    let (constant, targets) =
        crate::imports::constant_bound(files, (door.form, door.module, &door.evidence), bound)
            .map_err(DoorProblem::Constant)?;
    let edge = |target, package, resolved| {
        declared(declaration, door, (source, target, package), resolved)
    };
    let mut imports: Vec<Import> = targets
        .into_iter()
        .filter(|file| file.module.as_str() != door.module)
        .map(|file| edge(file.module.as_str(), file.package.as_str(), Resolved::Local))
        .collect();
    for prefix in declaration.loads().iter().flatten() {
        let prefix = prefix.as_text();
        let names = below(prefix);
        let top = prefix.split('.').next().unwrap_or(prefix);
        if names.is_empty() {
            let inside = files.keys().any(|module| in_scope(module, top));
            if inside {
                return Err(DoorProblem::LoadsNothing(prefix.to_owned()));
            }
            let resolved = if settings.standard(top) {
                Resolved::Builtin
            } else {
                Resolved::External(top.to_owned())
            };
            imports.push(edge(prefix, top, resolved));
        }
        for name in names.into_iter().filter(|name| *name != door.module) {
            let package = files.get(name).map_or("", |file| file.package.as_str());
            imports.push(edge(name, package, Resolved::Local));
        }
    }
    let applied = Applied {
        id: declaration.id().as_text().to_owned(),
        gap: door.gap.to_owned(),
        module: door.module.to_owned(),
        form: door.form,
        line: door.line,
        constant,
        loads: declaration
            .loads()
            .iter()
            .flatten()
            .map(|p| p.as_text().to_owned())
            .collect(),
        possible_loads: imports
            .iter()
            .filter(|import| import.resolved() == &Resolved::Local)
            .map(|import| import.target_module().to_owned())
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect(),
        changes: declaration
            .changes()
            .iter()
            .map(|p| p.as_text().to_owned())
            .collect(),
        effect: (!changed.is_empty()).then_some(GapEffect::Modules { modules: changed }),
        stated: door.effect.clone(),
    };
    Ok((applied, imports))
}

/// The declared import from the module of the door to `target`: a call that may run, with no
/// known name, cited by the evidence of the door site.
fn declared(
    declaration: &Declaration,
    door: &Door<'_>,
    (source_package, target, target_package): (&str, &str, &str),
    resolved: Resolved,
) -> Import {
    let id = stable_id(
        "DECLARED",
        &[
            Part::Text(declaration.id().as_text()),
            Part::Text(door.module),
            Part::Text(target),
        ],
    );
    let mut evidence = door.evidence.clone();
    evidence.sort_unstable();
    Import {
        id,
        declared: true,
        source_module: door.module.to_owned(),
        target_module: target.to_owned(),
        source_package: source_package.to_owned(),
        target_package: target_package.to_owned(),
        under_type_checking: false,
        symbol: None,
        symbols_known: false,
        call_form: true,
        call_by_name: true,
        published: Published {
            complete: true,
            ..Published::default()
        },
        relative: false,
        resolved,
        evidence,
        unbound_type: false,
    }
}

#[cfg(test)]
#[path = "door_reach_tests.rs"]
mod tests;
