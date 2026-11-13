// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Redundant record identities must agree before any consumer reads their payload (AD-408).

use archkeel_facts::data::SelectorData;
use archkeel_facts::vocab::{Area, ConstructForm, Operation, SelectorRole, Use};
use archkeel_facts::{ConstructFact, FactData, Record, ReferenceFact, Section, SymbolFact};

pub(crate) fn validate(section: &Section) -> Result<(), String> {
    match section {
        Section::Constructs(records) => {
            for record in records {
                construct(record)?;
            }
        }
        Section::TypingSignals(records) => {
            for record in records {
                let data = record.data.data();
                if record.kind().as_str() != data.signal.as_str() {
                    return Err("typing-signal kind disagrees with payload signal".to_owned());
                }
                if record.area != Area::TypeArchitecture {
                    return Err("typing-signal area disagrees with its section".to_owned());
                }
                if data
                    .qualified_name
                    .as_deref()
                    .is_some_and(|name| !in_owner(name, &data.owner))
                {
                    return Err("typing-signal qualified name disagrees with its owner".to_owned());
                }
            }
        }
        Section::References(records) => {
            for record in records {
                access(record)?;
            }
        }
        Section::Symbols(records) => {
            for record in records {
                subject(record)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn subject(record: &Record<SymbolFact>) -> Result<(), String> {
    let (name, qualified, category) = match &record.data {
        SymbolFact::Class(d) => (&d.name, &d.qualified_name, d.symbol_category),
        SymbolFact::Function(d) | SymbolFact::Method(d) => {
            (&d.name, &d.qualified_name, d.symbol_category)
        }
        _ => return Ok(()),
    };
    if category.as_str() != record.kind().as_str() {
        return Err("subject kind disagrees with payload symbol category".to_owned());
    }
    if qualified.rsplit('.').next() != Some(name.as_str()) {
        return Err("subject name disagrees with its qualified name".to_owned());
    }
    Ok(())
}

fn access(record: &Record<ReferenceFact>) -> Result<(), String> {
    let (usage, expected, area) = match &record.data {
        ReferenceFact::ValueReference(data) => (data.use_, Use::Value, Area::CallHierarchy),
        ReferenceFact::AttributeReference(data) => (data.use_, Use::Attribute, Area::CallHierarchy),
        ReferenceFact::SourceRole(data) => (data.use_, Use::SourceRole, Area::CallHierarchy),
        ReferenceFact::ScriptNamespaceEffect(data) => (data.use_, Use::Value, Area::Source),
        ReferenceFact::Reference(_) | ReferenceFact::References(_) => return Ok(()),
    };
    if usage != expected {
        return Err("access kind disagrees with payload use".to_owned());
    }
    if record.area != area {
        return Err("access record area disagrees with its kind".to_owned());
    }
    Ok(())
}

fn construct(record: &Record<ConstructFact>) -> Result<(), String> {
    if record
        .kind()
        .construct()
        .is_some_and(|expected| record.data.fields().construct != Some(expected))
    {
        return Err("source construct kind disagrees with payload construct".to_owned());
    }
    if record.area != Area::Constructs {
        return Err("construct record area disagrees with its section".to_owned());
    }
    match &record.data {
        ConstructFact::StringLiteralCompare(data) if data.form == Some(ConstructForm::Binary) => {
            Err("string comparison disagrees with its construct form".to_owned())
        }
        ConstructFact::BroadExcept(data)
        | ConstructFact::GetattrCall(data)
        | ConstructFact::HasattrCall(data)
        | ConstructFact::SetattrCall(data)
        | ConstructFact::DelattrCall(data)
        | ConstructFact::VarsCall(data)
            if data.form.is_some() =>
        {
            Err("access or exception record cannot have a comparison form".to_owned())
        }
        ConstructFact::ConstructSelector(data) if data.operation != operation(data) => {
            Err("selector role disagrees with its operation".to_owned())
        }
        ConstructFact::NumericOperand(data)
            if data.form != ConstructForm::Binary || data.operation != Operation::Modulo =>
        {
            Err("numeric operand disagrees with its form or operation".to_owned())
        }
        _ => Ok(()),
    }
}

fn operation(data: &SelectorData) -> Operation {
    match data.selector_role {
        SelectorRole::Read => Operation::Read,
        SelectorRole::Write => Operation::Write,
        SelectorRole::Call => Operation::Call,
        SelectorRole::Constructor => Operation::Construct,
        SelectorRole::Reflect | SelectorRole::TypeProbe => Operation::Probe,
        SelectorRole::Equality
        | SelectorRole::Membership
        | SelectorRole::Match
        | SelectorRole::Startswith
        | SelectorRole::Endswith => Operation::Compare,
    }
}

fn in_owner(name: &str, owner: &str) -> bool {
    let owner = owner.split(':').next().unwrap_or_default();
    name == owner
        || name
            .strip_prefix(owner)
            .is_some_and(|rest| rest.starts_with('.'))
}
