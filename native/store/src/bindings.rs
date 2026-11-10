// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `validate_source_bindings` of `ir/facts_validation.py` (AD-346): each source record and its
//! evidence belong to one observed module, a runtime-effect gap names its effect record, and a
//! typed import target agrees with its import record.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{Evidence, Facts, FileFact, Profile, Target};
use archkeel_facts::vocab::Status;
use archkeel_facts::{FactData, Record, Section};

use crate::pyrepr::stable_id;
use crate::stored::{visit, Visitor};
use crate::validate::unique;
use crate::view::View;

/// `in_scope` of `ir/facts.py`: a qualified name inside a dotted prefix.
fn in_scope(name: &str, scope: &str) -> bool {
    name == scope
        || name
            .strip_prefix(scope)
            .is_some_and(|rest| rest.starts_with('.'))
}

/// The observed modules of a reply: paths, packages, files and evidence by id.
pub(crate) struct Modules<'a> {
    files: HashMap<&'a str, &'a FileFact>,
    by_path: HashMap<&'a str, &'a str>,
    evidence: HashMap<&'a str, &'a Evidence>,
    part_evidence: bool,
}

/// The view of one record, found by its place.
struct One(Option<View>);

impl Visitor for One {
    fn record<D: FactData>(&mut self, _: &Section, record: &Record<D>) -> Result<(), String> {
        self.0 = Some(View::of(record)?);
        Ok(())
    }
}

impl<'a> Modules<'a> {
    pub(crate) fn of(facts: &'a Facts) -> Result<Self, String> {
        let paths = facts.files.iter().map(|file| file.rel_path.as_str());
        unique(paths, "module path")?;
        Ok(Modules {
            files: facts
                .files
                .iter()
                .map(|file| (file.module.as_str(), file))
                .collect(),
            by_path: facts
                .files
                .iter()
                .map(|file| (file.rel_path.as_str(), file.module.as_str()))
                .collect(),
            evidence: facts
                .evidence
                .iter()
                .map(|entry| (entry.id.as_str(), entry))
                .collect(),
            part_evidence: facts.profile == Profile::Dart,
        })
    }

    fn file(&self, id: &str) -> Option<&str> {
        self.evidence.get(id).map(|entry| entry.file.as_str())
    }

    fn source_module(&self, view: &View) -> Option<String> {
        let named = if view.kind == "module" {
            Some(view.data.qualified_name.clone())
        } else {
            view.data
                .source_module
                .clone()
                .or_else(|| view.data.module.clone())
        };
        match named {
            Some(Some(module)) => Some(module),
            // Python reads a null module like an absent one and falls back to the owner.
            _ => {
                view.data.owner.as_ref()?;
                let file = self.file(view.evidence_ids.first()?)?;
                self.by_path.get(file).map(|module| (*module).to_owned())
            }
        }
    }

    /// One record of a measured section: its module, its package, its identities and evidence.
    pub(crate) fn bind(
        &self,
        view: &View,
        import: bool,
        selected: &HashSet<&str>,
    ) -> Result<(), String> {
        if view.kind == "source_resolution_gap" {
            return match self.gap_module(view, None) {
                Some(_) => Ok(()),
                None => Err("source resolution gap has no bound resolution dimension".to_owned()),
            };
        }
        let module = self
            .source_module(view)
            .ok_or("source record needs an observed module or owner")?;
        let file = self
            .files
            .get(module.as_str())
            .ok_or("source record names an unobserved module")?;
        if import && view.data.source_package.as_deref() != Some(file.package.as_str()) {
            return Err("import source package disagrees with its module".to_owned());
        }
        let data = &view.data;
        for (field, identity) in [
            ("owner", &data.owner),
            ("source_scope", &data.source_scope),
            ("qualified_name", &data.qualified_name),
            ("declaration_scope", &data.declaration_scope),
        ] {
            let head = identity
                .as_deref()
                .map(|text| text.split(':').next().unwrap_or_default());
            if head.is_some_and(|head| !in_scope(head, &module)) {
                return Err(format!("source record {field} disagrees with its module"));
            }
        }
        let foreign = |id: &String| {
            let path = self.file(id);
            path != Some(file.rel_path.as_str())
                && !(self.part_evidence
                    && path.is_some()
                    && data.source_file.as_deref() == path
                    && path.is_some_and(|p| selected.contains(p) && !self.by_path.contains_key(p)))
        };
        if view.evidence_ids.is_empty() || view.evidence_ids.iter().any(foreign) {
            return Err("source record evidence disagrees with its module".to_owned());
        }
        Ok(())
    }

    /// `_resolution_gap_module`: the module of a witnessed resolution gap, or `None`. A
    /// runtime-effect gap needs its effect record (`effect`).
    fn gap_module(&self, gap: &View, effect: Option<&View>) -> Option<String> {
        let module = match &gap.data.source_module {
            Some(value) => value.clone()?,
            None => gap.data.module.clone()??,
        };
        let path = self.files.get(module.as_str())?.rel_path.as_str();
        let dimension = gap.data.resolution_dimension.as_deref();
        let agrees = |value: &Option<Option<String>>| {
            value
                .as_ref()
                .is_none_or(|value| value.as_deref() == Some(module.as_str()))
        };
        let witnessed = gap.kind == "source_resolution_gap"
            && matches!(dimension, Some("imports" | "runtime_effects"))
            && agrees(&gap.data.source_module)
            && agrees(&gap.data.module)
            && gap.subjects == [module.as_str()]
            && !gap.evidence_ids.is_empty()
            && gap
                .evidence_ids
                .iter()
                .all(|id| self.file(id) == Some(path))
            && gap.data.file.as_deref().is_none_or(|file| file == path);
        if !witnessed {
            return None;
        }
        if dimension == Some("runtime_effects") && !self.script_effect(gap, effect?, &module, path)
        {
            return None;
        }
        Some(module)
    }

    /// `_script_effect_binding`: the gap and its `script_namespace_effect` name one location.
    fn script_effect(&self, gap: &View, effect: &View, module: &str, path: &str) -> bool {
        let typescript = [".js", ".ts", ".tsx"]
            .iter()
            .any(|suffix| path.ends_with(suffix));
        let Some(location) = gap
            .evidence_ids
            .first()
            .and_then(|id| self.evidence.get(id.as_str()))
        else {
            return false;
        };
        let at = format!("{module}\u{1f}{}\u{1f}{}", location.line, location.column);
        typescript
            && gap.fact_ids.len() == 1
            && gap.evidence_ids.len() == 1
            && effect.id == stable_id("TS_RUNTIME_EFFECT", &at)
            && gap.id == stable_id("UNKNOWN_RUNTIME_EFFECT", &effect.id)
            && effect.kind == "script_namespace_effect"
            && effect.evidence_class == archkeel_facts::vocab::EvidenceClass::Fact
            && effect.subjects == [module]
            && effect.data.source_module == Some(Some(module.to_owned()))
            && effect.data.source_scope.as_deref() == Some(module)
            && effect.evidence_ids == gap.evidence_ids
            && effect.data.expression.as_deref() == Some(location.excerpt.as_str())
            && effect.data.status == Some(Status::Unresolved)
            && effect.data.targets.as_ref().is_some_and(Vec::is_empty)
    }

    /// A runtime-effect gap of the coverage is bound to its module and its effect record.
    pub(crate) fn effect_gap(
        &self,
        gap: &View,
        sections: &[Section],
        places: &HashMap<String, (usize, usize)>,
        script: bool,
    ) -> Result<(), String> {
        if gap.data.resolution_dimension.as_deref() != Some("runtime_effects") {
            return Ok(());
        }
        if gap.kind != "source_resolution_gap" {
            return self.bind(gap, false, &HashSet::new());
        }
        let mut effect = One(None);
        if let Some((section, index)) = gap.fact_ids.first().and_then(|id| places.get(id)) {
            visit(&sections[*section], *index, *index + 1, &mut effect)?;
        }
        let effect = effect.0.filter(|_| script);
        match self.gap_module(gap, effect.as_ref()) {
            Some(_) => Ok(()),
            None => Err("source resolution gap has no bound resolution dimension".to_owned()),
        }
    }

    /// A typed import target agrees with its import record and with the observed modules.
    pub(crate) fn target(
        &self,
        target: &Target,
        module: Option<&str>,
        package: Option<&str>,
        full_scope: bool,
        inputs: &HashSet<&str>,
    ) -> Result<(), String> {
        let local = module.is_some_and(|name| self.files.contains_key(name));
        let fail = |message: &str| Err(message.to_owned());
        match target {
            Target::Local {
                module: name,
                file,
                runtime_file,
                declaration_file,
                ..
            } => {
                let observed = self.files.get(name.as_str());
                if observed.is_none() && full_scope {
                    return fail("unobserved local target requires incomplete coverage");
                }
                if observed.is_some_and(|o| o.rel_path != *file) {
                    return fail("local import target disagrees with observed module");
                }
                if observed.is_some_and(|o| package != Some(o.package.as_str())) {
                    return fail("local import package disagrees with observed module");
                }
                let paths = [Some(file), runtime_file.as_ref(), declaration_file.as_ref()];
                if paths
                    .into_iter()
                    .flatten()
                    .any(|path| !inputs.contains(path.as_str()))
                {
                    return fail("local import target needs a digested input");
                }
                if module != Some(name.as_str()) {
                    return fail("local import target disagrees with import payload");
                }
            }
            Target::External { .. } if local => {
                return fail("observed local module cannot be an external target");
            }
            Target::External { package: name, .. } if package != Some(name.as_str()) => {
                return fail("external import target disagrees with import payload");
            }
            Target::Builtin { .. } if local => {
                return fail("observed local module cannot be a builtin target");
            }
            Target::Builtin { name, .. } if module != Some(name.as_str()) => {
                return fail("builtin import target disagrees with import payload");
            }
            Target::Unresolved { specifier, .. } if module != Some(specifier.as_str()) => {
                return fail("unresolved import target disagrees with import payload");
            }
            _ => {}
        }
        Ok(())
    }
}
