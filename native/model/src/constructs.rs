// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Construct observations and the matching receipt shared by the proof and evaluator (AD-408).

use archkeel_contract::ForbiddenConstruct;
use archkeel_facts::data::{SelectorData, SignalData};
use archkeel_facts::envelope::{ConstructSupport, Facts};
use archkeel_facts::vocab::{Kind, Status};
use archkeel_facts::{ConstructFact, FactData, Record, Section, SignalFact};

use crate::limits::word;
use crate::ownership::in_scope;
use crate::{Cause, Model, Reason};

/// One original observation. No rule result or completeness claim is stored here.
#[derive(Clone, Debug, PartialEq)]
pub struct ConstructSite {
    pub id: String,
    pub owner: String,
    pub construct: String,
    pub evidence: Vec<String>,
    signal: Option<SignalData>,
    selector: Option<SelectorData>,
}

/// The construct and symbol inventory of the reply, before contract selection.
#[derive(Debug)]
pub struct Constructs {
    sites: Vec<ConstructSite>,
    symbols: Vec<(String, String)>,
    capabilities: Vec<(String, ConstructSupport)>,
    selectors: bool,
}

/// One matched site and whether its selected identity is proven.
#[derive(Debug)]
pub struct ConstructMatch<'a> {
    pub site: &'a ConstructSite,
    pub known: bool,
}

/// One bounded walk over input. Exhaustion withholds the receipt and the verdict.
struct Work(usize);

impl Work {
    fn charge(&mut self, count: usize) -> Result<(), Reason> {
        self.0 = self
            .0
            .checked_sub(count)
            .ok_or(Reason::TooManyRows("construct work"))?;
        Ok(())
    }
}

impl Constructs {
    pub(crate) fn derive(facts: &Facts) -> Result<Self, Reason> {
        let mut found = Self {
            sites: Vec::new(),
            symbols: Vec::new(),
            capabilities: Vec::new(),
            selectors: facts.profile.construct_selectors(),
        };
        let mut work = Work(4_000_000);
        for capability in &facts.capabilities.constructs {
            work.charge(1)?;
            found
                .capabilities
                .push((capability.name.clone(), capability.status));
        }
        for section in &facts.sections {
            work.charge(1)?;
            match section {
                Section::Constructs(records) => {
                    for record in records {
                        work.charge(1)?;
                        if let Some(site) = construct(record) {
                            found.sites.push(site);
                        }
                    }
                }
                Section::TypingSignals(records) => {
                    for record in records {
                        work.charge(1)?;
                        let data = signal(&record.data);
                        if let Some(name) = data.signal.construct() {
                            found.sites.push(site(
                                record,
                                name,
                                &data.owner,
                                Some(data.clone()),
                                None,
                            ));
                        }
                    }
                }
                Section::Symbols(records) => {
                    for record in records {
                        work.charge(1)?;
                        if matches!(
                            record.data.kind(),
                            Kind::Class | Kind::Function | Kind::Method
                        ) {
                            let fields = record.data.fields();
                            if let (Some(Some(module)), Some(name)) =
                                (fields.module, fields.qualified_name)
                            {
                                found.symbols.push((module.to_owned(), name.to_owned()));
                            }
                        }
                    }
                }
                _ => {}
            }
        }
        Ok(found)
    }

    /// Actual owner names with their physical modules. A name outside its module is not a subject.
    pub(crate) fn symbols(&self) -> &[(String, String)] {
        &self.symbols
    }

    /// Matching forbidden sites; a literal conflict of a proven selector is not forbidden.
    pub fn matches<'a>(
        &'a self,
        model: &Model,
        rule: &ForbiddenConstruct,
    ) -> Result<Vec<ConstructMatch<'a>>, Reason> {
        let mut work = Work(4_000_000);
        let mut found = Vec::new();
        for site in &self.sites {
            work.charge(1)?;
            work.charge(model.graph().modules().len())?;
            work.charge(rule.allowed_sources().len())?;
            work.charge(rule.exact_sources().len())?;
            work.charge(rule.constructs().len())?;
            work.charge(rule.allowed_type_ignores().len())?;
            if !selected(model, rule, site) {
                continue;
            }
            match (rule.selector(), &site.selector) {
                (Some(selector), Some(data)) => {
                    if data.selector_role.as_str() != word(selector.role())
                        || data
                            .receiver_type
                            .as_deref()
                            .is_some_and(|r| r != selector.receiver().as_text())
                        || selector.member().as_ref().is_some_and(|member| {
                            data.member.as_ref() != Some(member)
                                && !(data.member.is_none() && data.status == Status::Unknown)
                        })
                    {
                        continue;
                    }
                    let known = data.status == Status::Decided
                        && data.receiver_type.as_deref() == Some(selector.receiver().as_text());
                    let conflict = selector.literal().is_some()
                        && data.literal.is_some()
                        && selector.literal() != &data.literal;
                    let literal_matches =
                        selector.literal().is_none() || selector.literal() == &data.literal;
                    if !(known && conflict) {
                        found.push(ConstructMatch {
                            site,
                            known: known && literal_matches,
                        });
                    }
                }
                (None, None) => {
                    if rule.constructs().iter().any(|c| word(c) == site.construct)
                        && !allowed_ignore(rule, site)
                    {
                        found.push(ConstructMatch { site, known: true });
                    }
                }
                _ => {}
            }
        }
        Ok(found)
    }

    pub(crate) fn receipt(&self, model: &Model, rule: &ForbiddenConstruct) -> Result<(), Reason> {
        let mut work = Work(4_000_000);
        let modules = model.graph().modules().len();
        work.charge(self.symbols.len().saturating_mul(modules.saturating_add(1)))?;
        work.charge(modules.saturating_mul(model.components().len().saturating_add(1)))?;
        if model.source_modules(rule.source().as_text()).is_empty()
            && !self.symbols.iter().any(|(module, name)| {
                model.selects(module)
                    && in_scope(name, module)
                    && model
                        .graph()
                        .modules()
                        .iter()
                        .any(|(_, m)| m.name() == module)
                    && in_scope(name, rule.source().as_text())
            })
        {
            return Err(Reason::NoSubjects);
        }
        for construct in rule.constructs() {
            work.charge(self.capabilities.len().saturating_add(1))?;
            let support = self
                .capabilities
                .iter()
                .find(|(name, _)| name == &word(construct));
            if !matches!(support, Some((_, ConstructSupport::Supported))) {
                return Err(Cause::Receipt("construct absence is not completely observed").into());
            }
        }
        if let Some(selector) = rule.selector() {
            if !self.selectors || !model.graph().observed().inventory_complete {
                return Err(Cause::Receipt("the selector inventory is not complete").into());
            }
            let matches = self.matches(model, rule)?;
            if matches.iter().any(|m| !m.known) {
                return Err(Cause::Receipt("unresolved selected identity").into());
            }
            // A proven different literal is a selected subject too, but not a violation.
            let mut any = false;
            for site in &self.sites {
                work.charge(
                    modules
                        .saturating_add(rule.allowed_sources().len())
                        .saturating_add(rule.exact_sources().len())
                        .saturating_add(1),
                )?;
                if !selected(model, rule, site) {
                    continue;
                }
                if let Some(data) = &site.selector {
                    any |= data.selector_role.as_str() == word(selector.role())
                        && data.receiver_type.as_deref() == Some(selector.receiver().as_text())
                        && data.member == *selector.member()
                        && data.status == Status::Decided;
                }
            }
            if !any {
                return Err(Cause::Receipt("no selected subject was observed").into());
            }
        }
        Ok(())
    }
}

fn selected(model: &Model, rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    let owner = site.owner.split(':').next().unwrap_or_default();
    model
        .graph()
        .modules()
        .iter()
        .any(|(id, module)| model.holds(id) && in_scope(&site.owner, module.name()))
        && in_scope(owner, rule.source().as_text())
        && !rule
            .allowed_sources()
            .iter()
            .any(|a| in_scope(owner, a.as_text()))
        && !rule.exact_sources().iter().any(|a| a.as_text() == owner)
}

fn allowed_ignore(rule: &ForbiddenConstruct, site: &ConstructSite) -> bool {
    let Some(data) = &site.signal else {
        return false;
    };
    if data.signal != archkeel_facts::vocab::Signal::TypeIgnore {
        return false;
    }
    rule.allowed_type_ignores().iter().any(|a| {
        data.qualified_name.as_deref() == Some(a.qualified_name().as_text())
            && data.line.and_then(|n| u64::try_from(n).ok()) == Some(*a.line())
            && data.statement.as_deref() == Some(a.statement().as_str())
            && data.tag.as_deref() == Some(a.tag().as_str())
    })
}

fn site<D>(
    record: &Record<D>,
    construct: &str,
    owner: &str,
    signal: Option<SignalData>,
    selector: Option<SelectorData>,
) -> ConstructSite {
    ConstructSite {
        id: record.id.as_str().to_owned(),
        owner: owner.to_owned(),
        construct: construct.to_owned(),
        evidence: record
            .evidence_ids
            .iter()
            .map(|e| e.as_str().to_owned())
            .collect(),
        signal,
        selector,
    }
}

fn construct(record: &Record<ConstructFact>) -> Option<ConstructSite> {
    let selector = match &record.data {
        ConstructFact::ConstructSelector(data) => Some(data.clone()),
        _ => None,
    };
    let fields = record.data.fields();
    Some(site(
        record,
        fields.construct?,
        fields.owner?,
        None,
        selector,
    ))
}

fn signal(record: &SignalFact) -> &SignalData {
    match record {
        SignalFact::AnyAnnotation(d)
        | SignalFact::DictAnyAnnotation(d)
        | SignalFact::CallableAnyAnnotation(d)
        | SignalFact::ObjectAnnotation(d)
        | SignalFact::CastCall(d)
        | SignalFact::GetattrCall(d)
        | SignalFact::HasattrCall(d)
        | SignalFact::EvalCall(d)
        | SignalFact::ExecCall(d)
        | SignalFact::DynamicImport(d)
        | SignalFact::TypeIgnore(d)
        | SignalFact::MissingCrossPackageAnnotation(d) => d,
    }
}
