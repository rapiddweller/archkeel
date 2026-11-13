// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply's construct inventory, below the graph and contract matching (AD-408).

use archkeel_facts::data::{SelectorData, SignalData};
use archkeel_facts::envelope::{ConstructSupport, Facts};
use archkeel_facts::vocab::Kind;
use archkeel_facts::{ConstructFact, FactData, Record, Section, SignalFact};

use crate::Reason;

/// One original observation. No rule result or completeness claim is stored here.
#[derive(Clone, Debug, PartialEq)]
pub struct ConstructSite {
    pub id: String,
    pub owner: String,
    pub construct: String,
    pub evidence: Vec<String>,
    pub(crate) signal: Option<SignalData>,
    pub(crate) selector: Option<SelectorData>,
}

/// The construct and symbol inventory of the reply, before contract selection.
#[derive(Debug)]
pub struct Constructs {
    pub(crate) sites: Vec<ConstructSite>,
    pub(crate) symbols: Vec<(String, String)>,
    pub(crate) capabilities: Vec<(String, ConstructSupport)>,
    pub(crate) selectors: bool,
    pub(crate) constructs_measured: bool,
    pub(crate) signals_measured: bool,
}

/// One matched site and whether its selected identity is proven.
#[derive(Debug)]
pub struct ConstructMatch<'a> {
    pub site: &'a ConstructSite,
    pub known: bool,
}

/// One bounded walk over input. Exhaustion withholds the receipt and the verdict.
pub(crate) struct Work(pub(crate) usize);

impl Work {
    pub(crate) fn charge(&mut self, count: usize) -> Result<(), Reason> {
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
            constructs_measured: false,
            signals_measured: false,
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
            collect(&mut found, section, &mut work)?;
        }
        work.charge(found.sites.len().saturating_mul(32))?;
        found.sites.sort_by_key(|site| site.signal.is_none());
        Ok(found)
    }

    /// Actual owner names with their physical modules. A name outside its module is not a subject.
    pub(crate) fn symbols(&self) -> &[(String, String)] {
        &self.symbols
    }
}

fn collect(found: &mut Constructs, section: &Section, work: &mut Work) -> Result<(), Reason> {
    match section {
        Section::Constructs(records) => {
            found.constructs_measured = true;
            for record in records {
                work.charge(record.evidence_ids.len().saturating_add(1))?;
                if let Some(site) = construct(record) {
                    found.sites.push(site);
                }
            }
        }
        Section::TypingSignals(records) => {
            found.signals_measured = true;
            for record in records {
                let data = signal(&record.data);
                work.charge(record.evidence_ids.len().saturating_add(1))?;
                work.charge(data.positions.as_ref().map_or(0, Vec::len))?;
                if let Some(name) = data.signal.construct() {
                    found
                        .sites
                        .push(site(record, name, &data.owner, Some(data.clone()), None));
                }
            }
        }
        Section::Symbols(records) => {
            for record in records {
                work.charge(1)?;
                if !matches!(
                    record.data.kind(),
                    Kind::Class | Kind::Function | Kind::Method
                ) {
                    continue;
                }
                let fields = record.data.fields();
                if let (Some(Some(module)), Some(name)) = (fields.module, fields.qualified_name) {
                    found.symbols.push((module.to_owned(), name.to_owned()));
                }
            }
        }
        _ => {}
    }
    Ok(())
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
