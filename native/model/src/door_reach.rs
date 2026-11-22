// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declared reach of trojan horse sites (AD-664, AD-1052). A trojan horse is a place that can
//! load code the scan does not see; it is not a claim of malice. A contract names one site by form
//! or by name, and the prefixes that it may load or change. A declaration that matches its sites
//! with a valid reach is applied; each other one is a problem and applies nothing. It reads
//! collector metadata, not source code.

use std::collections::{BTreeMap, HashMap};

use archkeel_contract::TrojanHorseReach as Declaration;
use archkeel_facts::data::{GapEffect, TrojanHorseForm};
use archkeel_facts::envelope::{Facts, FileFact};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::ModuleName;

use crate::coverage::data_of;
use crate::gap_class::EffectGap;
use crate::imports::{Import, Published, Resolved};
use crate::ownership::in_scope;
use crate::settings::Settings;

/// One applied declaration: the site, the gap and the reach.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Applied {
    /// The id of the declaration.
    pub id: String,
    /// Why the reach holds.
    pub rationale: String,
    /// The id of the gap of the trojan horse.
    pub gap: String,
    /// The module of the trojan horse.
    pub module: String,
    /// The form word of the trojan horse, or the name of the site.
    pub label: String,
    /// The form of the trojan horse; none for a site named by its name.
    pub form: Option<TrojanHorseForm>,
    /// The line of the trojan horse site.
    pub line: u32,
    /// The declared module prefixes that the trojan horse may import.
    pub loads: Vec<String>,
    /// The source binding and template of a constant-bound declaration.
    pub constant: Option<String>,
    /// The possible dependency edges that the declaration supplies, from the module of the site:
    /// the scanned target and the id of the declared import (AD-1057).
    pub edges: Vec<(String, String)>,
    /// The declared module prefixes whose names the trojan horse may change.
    pub changes: Vec<String>,
    /// The modules that reach the bound name and that `covers` names (AD-1056).
    pub covered: Vec<String>,
    /// What the gap still leaves unknown under the premise, or `None` for nothing.
    pub(crate) effect: Option<GapEffect>,
    pub(crate) stated: GapEffect,
}

impl Applied {
    /// `D-1 (pkg.mod:12 eval)`: the declaration and its site, for a reader.
    pub fn site(&self) -> String {
        let site = format!("{} ({}:{} {})", self.id, self.module, self.line, self.label);
        match &self.constant {
            Some(bound) => format!("{site}: loads only the targets from {bound}"),
            None => site,
        }
    }

    /// The form word of the trojan horse, or the name that the declaration gives the site.
    pub fn trojan_horse(&self) -> &str {
        match self.form {
            Some(form) => form.word(),
            None => &self.label,
        }
    }
}

/// Why one declaration is not applied.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TrojanHorseProblem {
    /// No trojan horse of the reply has this site: it moved, changed its form or is gone.
    Unmatched,
    /// More than one trojan horse has this site: their number.
    Ambiguous(usize),
    /// The site has more than one declaration: the ids of the others.
    Repeated(Vec<String>),
    /// The word names no form of a trojan horse.
    Form,
    /// A `changes` prefix holds no module of the scan.
    ChangesOutside(String),
    /// A `loads` prefix lies in a top package of the scan and holds no module of it.
    LoadsNothing(String),
    /// These modules can reach the name that the site binds.
    Exported(Vec<String>),
    /// The gap covers this number of unresolved imports.
    Unresolved(usize),
    /// The scanned evidence does not establish a usable constant bound.
    Constant(String),
}

impl TrojanHorseProblem {
    /// The stable code of the problem, for its row.
    pub fn code(&self) -> &'static str {
        match self {
            TrojanHorseProblem::Unmatched => "trojan_horse_reach.unmatched",
            TrojanHorseProblem::Ambiguous(_) => "trojan_horse_reach.ambiguous",
            TrojanHorseProblem::Repeated(_) => "trojan_horse_reach.repeated",
            TrojanHorseProblem::Form
            | TrojanHorseProblem::ChangesOutside(_)
            | TrojanHorseProblem::LoadsNothing(_)
            | TrojanHorseProblem::Exported(_)
            | TrojanHorseProblem::Constant(_)
            | TrojanHorseProblem::Unresolved(_) => "trojan_horse_reach.invalid",
        }
    }

    /// What the problem is, for a reader.
    pub fn text(&self) -> String {
        match self {
            TrojanHorseProblem::Unmatched => "matches no trojan horse of the scan (moved, changed or gone); \
                 the declaration is not applied"
                .to_owned(),
            TrojanHorseProblem::Ambiguous(n) => format!("matches {n} trojan horses; name the site by its line; the declaration is not applied"),
            TrojanHorseProblem::Repeated(o) => format!("names a trojan horse that {} also name; the declarations of the trojan horse are not applied", o.join(", ")),
            TrojanHorseProblem::Form => format!(
                "names no form of a trojan horse; the forms are {}; the declaration is not applied",
                TrojanHorseForm::ALL.map(TrojanHorseForm::word).join(", ")
            ),
            TrojanHorseProblem::ChangesOutside(prefix) => format!(
                "changes {prefix}, which holds no module of the scan; a change outside the \
                 scan can change any import; the declaration is not applied"
            ),
            TrojanHorseProblem::Exported(importers) => format!(
                "binds the trojan horse to a name that {} import, so the trojan horse runs outside its module; \
                 the declaration is not applied",
                importers.join(", ")
            ),
            TrojanHorseProblem::Unresolved(n) => format!("names a trojan horse whose gap covers {n} imports that the scan cannot resolve; a declared reach does not resolve them; the declaration is not applied"),
            TrojanHorseProblem::LoadsNothing(p) => format!("loads {p}, which lies in the project and holds no module of the scan; the declaration is not applied"),
            TrojanHorseProblem::Constant(reason) => format!("{reason}; the declaration is not applied"),
        }
    }
}

/// The declarations of a run, matched to the trojan horses of its reply.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct TrojanHorses {
    applied: Vec<Applied>,
    problems: Vec<(usize, String, TrojanHorseProblem)>,
    imports: Vec<Import>,
}

impl TrojanHorses {
    /// Each applied declaration, in contract order.
    pub fn applied(&self) -> &[Applied] {
        &self.applied
    }

    /// Each declaration that is not applied: its index, its id and the problem.
    pub fn problems(&self) -> &[(usize, String, TrojanHorseProblem)] {
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
pub(crate) fn narrowed(trojan_horses: &TrojanHorses, gaps: Vec<EffectGap>) -> Vec<EffectGap> {
    gaps.into_iter()
        .filter_map(|gap| match trojan_horses.of_gap(&gap.id) {
            None => Some(gap),
            Some(applied) => applied
                .effect
                .clone()
                .map(|effect| EffectGap { id: gap.id, effect }),
        })
        .collect()
}

/// One trojan horse of the reply.
struct TrojanHorse<'f> {
    gap: &'f str,
    module: &'f str,
    form: Option<TrojanHorseForm>,
    name: Option<&'f str>,
    line: u32,
    scope: Option<&'f str>,
    exposed: &'f [String],
    effect: &'f GapEffect,
    evidence: Vec<String>,
    binding: Option<&'f str>,
}

/// Match the declarations to the trojan horses of `facts`.
pub(crate) fn matched(
    declared: &[Declaration],
    facts: &Facts,
    settings: &Settings,
) -> TrojanHorses {
    let trojan_horses: Vec<TrojanHorse<'_>> = facts
        .coverage
        .gaps
        .iter()
        .filter_map(trojan_horse)
        .collect();
    let mut found = TrojanHorses::default();
    let mut by_gap: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
    let mut matches: Vec<(usize, &TrojanHorse<'_>)> = Vec::new();
    for (index, declaration) in declared.iter().enumerate() {
        let problem = |found: &mut TrojanHorses, problem| {
            let id = declaration.id().as_text().to_owned();
            found.problems.push((index, id, problem))
        };
        let sites: Vec<&TrojanHorse<'_>> = if String::is_empty(declaration.trojan_horse()) {
            trojan_horses
                .iter()
                .filter(|horse| named(horse, declaration))
                .collect()
        } else {
            let Some(form) = TrojanHorseForm::of_word(declaration.trojan_horse()) else {
                problem(&mut found, TrojanHorseProblem::Form);
                continue;
            };
            trojan_horses
                .iter()
                .filter(|horse| at(horse, declaration, form))
                .collect()
        };
        let count = (*declaration.site_count()).map_or(1, |n| usize::try_from(n).unwrap_or(0));
        match sites.as_slice() {
            [] => problem(&mut found, TrojanHorseProblem::Unmatched),
            many if many.len() == count => {
                for horse in many {
                    by_gap.entry(horse.gap).or_default().push(index);
                    matches.push((index, horse));
                }
            }
            many if many.len() < count => problem(&mut found, TrojanHorseProblem::Unmatched),
            many => problem(&mut found, TrojanHorseProblem::Ambiguous(many.len())),
        }
    }
    let unresolved = crate::imports::covered(facts);
    let files: HashMap<&str, &FileFact> = facts
        .files
        .iter()
        .map(|file| (file.module.as_str(), file))
        .collect();
    for (index, horse) in matches {
        let declaration = &declared[index];
        let id = declaration.id().as_text().to_owned();
        let shared = &by_gap[horse.gap];
        let reach = (horse.binding).map_or_else(Vec::new, |binding| {
            crate::imports::importers(facts, (horse.module, binding), horse.exposed)
        });
        // `covers` names the modules whose use of the bound name the contract accepts (AD-1056).
        let covers = declaration.covers().iter();
        let at = |name: &String| {
            covers
                .clone()
                .any(|prefix| in_scope(name, prefix.as_text()))
        };
        let (covered, blocking): (Vec<String>, Vec<String>) = reach.into_iter().partition(at);
        let refused = if shared.len() > 1 {
            let others = shared.iter().filter(|other| **other != index);
            let others = others.map(|other| declared[*other].id().as_text().to_owned());
            Some(TrojanHorseProblem::Repeated(others.collect()))
        } else if let Some(count) = unresolved.get(horse.gap) {
            Some(TrojanHorseProblem::Unresolved(*count))
        } else if !blocking.is_empty() {
            Some(TrojanHorseProblem::Exported(blocking))
        } else {
            None
        };
        match refused.map_or_else(|| apply(declaration, horse, &files, settings), Err) {
            Ok((mut applied, imports)) => {
                applied.covered = covered;
                found.applied.push(applied);
                found.imports.extend(imports);
            }
            Err(problem) => found.problems.push((index, id, problem)),
        }
    }
    found.problems.sort_by_key(|(index, _, _)| *index);
    found.problems.dedup_by_key(|(index, _, _)| *index);
    found.imports.sort_by(|a, b| a.id.cmp(&b.id));
    found.imports.dedup_by(|a, b| a.id == b.id);
    found
}

/// The trojan horse of a gap, when the collector marks one and names its module and its effect.
fn trojan_horse(gap: &archkeel_facts::Record<archkeel_facts::GapFact>) -> Option<TrojanHorse<'_>> {
    let data = data_of(&gap.data);
    let site = data.trojan_horse.as_ref()?;
    Some(TrojanHorse {
        gap: gap.id.as_str(),
        module: data.module.as_ref()?.as_str(),
        form: site.form,
        name: Option::as_deref(&site.site_name),
        exposed: &site.exposed_to,
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

/// True when the declaration names this trojan horse by form, line and scope.
fn at(horse: &TrojanHorse<'_>, declaration: &Declaration, form: TrojanHorseForm) -> bool {
    horse.module == declaration.module().as_text()
        && horse.form == Some(form)
        && declaration
            .line()
            .is_none_or(|line| u64::from(horse.line) == line)
        && declaration
            .scope()
            .as_deref()
            .is_none_or(|scope| horse.scope == Some(scope))
}

/// True when the declaration names this trojan horse by name, line and scope (AD-1052).
fn named(horse: &TrojanHorse<'_>, declaration: &Declaration) -> bool {
    let name: &Option<String> = declaration.site_name();
    horse.module == declaration.module().as_text()
        && horse.name == Option::as_deref(name)
        && declaration
            .line()
            .is_none_or(|line| u64::from(horse.line) == line)
        && declaration
            .scope()
            .as_deref()
            .is_none_or(|scope| horse.scope == Some(scope))
}

/// The applied declaration and its declared imports, or the problem of its reach.
fn apply(
    declaration: &Declaration,
    horse: &TrojanHorse<'_>,
    files: &HashMap<&str, &FileFact>,
    settings: &Settings,
) -> Result<(Applied, Vec<Import>), TrojanHorseProblem> {
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
            return Err(TrojanHorseProblem::ChangesOutside(
                prefix.as_text().to_owned(),
            ));
        }
        changed.extend(names.into_iter().map(ModuleName::new));
    }
    changed.sort_by(|a, b| a.as_str().cmp(b.as_str()));
    changed.dedup();
    let source = files
        .get(horse.module)
        .map_or("", |file| file.package.as_str());
    let bound = declaration.loads_from().as_ref().map(|bound| {
        (
            bound.constant().as_str(),
            bound.template().as_str(),
            bound.call().as_str(),
        )
    });
    let (constant, targets) =
        crate::imports::constant_bound(files, (horse.form, horse.module, &horse.evidence), bound)
            .map_err(TrojanHorseProblem::Constant)?;
    let edge = |target, package, resolved| {
        declared(declaration, horse, (source, target, package), resolved)
    };
    let mut imports: Vec<Import> = targets
        .into_iter()
        .filter(|file| file.module.as_str() != horse.module)
        .map(|file| edge(file.module.as_str(), file.package.as_str(), Resolved::Local))
        .collect();
    for prefix in declaration.loads().iter().flatten() {
        let prefix = prefix.as_text();
        let names = below(prefix);
        let top = prefix.split('.').next().unwrap_or(prefix);
        if names.is_empty() {
            let inside = files.keys().any(|module| in_scope(module, top));
            if inside {
                return Err(TrojanHorseProblem::LoadsNothing(prefix.to_owned()));
            }
            let resolved = if settings.standard(top) {
                Resolved::Builtin
            } else {
                Resolved::External(top.to_owned())
            };
            imports.push(edge(prefix, top, resolved));
        }
        for name in names.into_iter().filter(|name| *name != horse.module) {
            let package = files.get(name).map_or("", |file| file.package.as_str());
            imports.push(edge(name, package, Resolved::Local));
        }
    }
    let site = Some(declaration.trojan_horse().clone()).filter(|word| !String::is_empty(word));
    let site = site.or_else(|| Option::clone(declaration.site_name()));
    let applied = Applied {
        id: declaration.id().as_text().to_owned(),
        rationale: declaration.rationale().to_owned(),
        gap: horse.gap.to_owned(),
        module: horse.module.to_owned(),
        form: horse.form,
        label: site.unwrap_or_default(),
        line: horse.line,
        constant,
        loads: declaration
            .loads()
            .iter()
            .flatten()
            .map(|p| p.as_text().to_owned())
            .collect(),
        edges: imports
            .iter()
            .filter(|import| import.resolved() == &Resolved::Local)
            .map(|import| (import.target_module().to_owned(), import.id().to_owned()))
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect(),
        changes: declaration
            .changes()
            .iter()
            .map(|p| p.as_text().to_owned())
            .collect(),
        effect: (!changed.is_empty()).then_some(GapEffect::Modules { modules: changed }),
        covered: Vec::new(),
        stated: horse.effect.clone(),
    };
    Ok((applied, imports))
}

/// The declared import from the module of the trojan horse to `target`: a call that may run, with no
/// known name, cited by the evidence of the trojan horse site.
fn declared(
    declaration: &Declaration,
    horse: &TrojanHorse<'_>,
    (source_package, target, target_package): (&str, &str, &str),
    resolved: Resolved,
) -> Import {
    let id = stable_id(
        "DECLARED",
        &[
            Part::Text(declaration.id().as_text()),
            Part::Text(horse.module),
            Part::Text(target),
        ],
    );
    let mut evidence = horse.evidence.clone();
    evidence.sort_unstable();
    Import {
        id,
        declared: true,
        source_module: horse.module.to_owned(),
        target_module: target.to_owned(),
        source_package: source_package.to_owned(),
        target_package: target_package.to_owned(),
        under_type_checking: false,
        symbol: None,
        symbols_known: false,
        inferred_receiver: false,
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
#[path = "trojan_horse_reach_tests.rs"]
mod tests;
