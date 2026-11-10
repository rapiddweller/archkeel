// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sections of a reply and the kinds that each section holds.
//!
//! The section decides the data type of a kind: `dynamic_import` is an import in `imports` and a
//! typing signal in `typing_signals`. A kind that its section does not hold is a decode error.

use schemars::{JsonSchema, Schema, SchemaGenerator};
use serde::de::Error as _;
use serde::ser::{SerializeMap, Serializer};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{json, Value};

use crate::data::{
    BindingData, CallData, CallableData, ClassData, ConstructData, GapData, ImportData,
    NumericOperandData, ReferenceData, SelectorData, SignalData, SourceRoleData, UnusedBindingData,
    ValueData,
};
use crate::readset::{self, ReadFields, ReadSet, Reads};
use crate::record::{FactData, Record};
use crate::vocab::{ExceptionName, Kind};

/// The data of a section: it gives the section that holds its records.
pub trait IntoSection: FactData {
    fn section(records: Vec<Record<Self>>) -> Section;

    /// The name of the section on the wire.
    fn section_name() -> &'static str {
        Self::section(Vec::new()).name()
    }

    /// The records of `section`, when it is the section of this data.
    fn records(section: &Section) -> Option<&[Record<Self>]>;
}

impl IntoSection for GapFact {
    fn section(records: Vec<Record<Self>>) -> Section {
        Section::Unknowns(records)
    }

    fn records(section: &Section) -> Option<&[Record<Self>]> {
        match section {
            Section::Unknowns(records) => Some(records),
            _ => None,
        }
    }
}

section_facts! {
    pub enum ImportFact in Imports {
        Import(ImportData),
        Reexport(ImportData),
        ImportType(ImportData),
        ImportEquals(ImportData),
        Require(ImportData),
        DynamicImport(ImportData),
        ScriptGlobal(ImportData),
        MacroBody(ImportData),
    }
}

/// The data of an import record: each import kind has the same data type.
macro_rules! import_data {
    ($fact:expr) => {
        match $fact {
            ImportFact::Import(data)
            | ImportFact::Reexport(data)
            | ImportFact::ImportType(data)
            | ImportFact::ImportEquals(data)
            | ImportFact::Require(data)
            | ImportFact::DynamicImport(data)
            | ImportFact::ScriptGlobal(data)
            | ImportFact::MacroBody(data) => data,
        }
    };
}

impl ImportFact {
    /// The data of the import; every import kind has the same data type.
    pub fn data(&self) -> &ImportData {
        import_data!(self)
    }

    pub fn data_mut(&mut self) -> &mut ImportData {
        import_data!(self)
    }
}

section_facts! {
    pub enum SymbolFact in Symbols {
        Class(ClassData),
        Function(CallableData),
        Method(CallableData),
        Constant(ValueData),
        TypeAlias(ValueData),
        Binding(ValueData),
        Alias(ValueData),
        DynamicBinding(ValueData),
        StaticConstant(ValueData),
        Macro(ValueData),
    }
}

section_facts! {
    pub enum CallFact in Calls {
        Calls(CallData),
        Call(CallData),
        ResolvedCall(CallData),
        PartiallyResolvedCall(CallData),
        UnresolvedCall(CallData),
    }
}

section_facts! {
    pub enum ReferenceFact in References {
        References(ReferenceData),
        Reference(ReferenceData),
        ScriptNamespaceEffect(ReferenceData),
        ValueReference(ReferenceData),
        AttributeReference(ReferenceData),
        SourceRole(SourceRoleData),
    }
}

section_facts! {
    pub enum BindingFact in Bindings {
        Bindings(BindingData),
        UnusedParameter(UnusedBindingData),
        UnusedLocal(UnusedBindingData),
    }
}

section_facts! {
    pub enum ConstructFact in Constructs {
        StringLiteralCompare(ConstructData),
        BroadExcept(ConstructData),
        GetattrCall(ConstructData),
        HasattrCall(ConstructData),
        SetattrCall(ConstructData),
        DelattrCall(ConstructData),
        VarsCall(ConstructData),
        ConstructSelector(SelectorData),
        NumericOperand(NumericOperandData),
    }
}

section_facts! {
    pub enum SignalFact in TypingSignals {
        AnyAnnotation(SignalData),
        DictAnyAnnotation(SignalData),
        CallableAnyAnnotation(SignalData),
        ObjectAnnotation(SignalData),
        CastCall(SignalData),
        GetattrCall(SignalData),
        HasattrCall(SignalData),
        EvalCall(SignalData),
        ExecCall(SignalData),
        DynamicImport(SignalData),
        TypeIgnore(SignalData),
        MissingCrossPackageAnnotation(SignalData),
    }
}

/// A gap of the coverage or of the `unknowns` section.
#[derive(Clone, Debug, PartialEq)]
pub enum GapFact {
    CollectionGap(GapData),
    SourceResolutionGap(GapData),
    DynamicImportLimit(GapData),
    PrivateAttributeAccessLimit(GapData),
    /// An analyzer failure. Protocol 9 writes the exception class name as the kind.
    ExceptionGap {
        exception: ExceptionName,
        data: GapData,
    },
}

impl GapFact {
    fn data(&self) -> &GapData {
        match self {
            GapFact::CollectionGap(data)
            | GapFact::SourceResolutionGap(data)
            | GapFact::DynamicImportLimit(data)
            | GapFact::PrivateAttributeAccessLimit(data)
            | GapFact::ExceptionGap { data, .. } => data,
        }
    }
}

impl FactData for GapFact {
    const NAME: &'static str = "GapFact";

    fn kind(&self) -> Kind {
        match self {
            GapFact::CollectionGap(_) => Kind::CollectionGap,
            GapFact::SourceResolutionGap(_) => Kind::SourceResolutionGap,
            GapFact::DynamicImportLimit(_) => Kind::DynamicImportLimit,
            GapFact::PrivateAttributeAccessLimit(_) => Kind::PrivateAttributeAccessLimit,
            GapFact::ExceptionGap { .. } => Kind::ExceptionGap,
        }
    }

    fn wire_kind(&self) -> &str {
        match self {
            GapFact::ExceptionGap { exception, .. } => exception.as_str(),
            other => other.kind().as_str(),
        }
    }

    fn fields(&self) -> crate::fields::Fields<'_> {
        crate::fields::Project::fields(self.data())
    }

    fn serialize_data<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.data().serialize(serializer)
    }

    /// An analyzer failure adds its exception name: the closed kind does not hold it. A reason
    /// code is protocol 10 data that no WP1 reader can have read; it is written when it is set.
    fn read_set_entries<M: SerializeMap>(&self, map: &mut M, reads: Reads) -> Result<(), M::Error> {
        if let GapFact::ExceptionGap { exception, .. } = self {
            map.serialize_entry("exception", exception)?;
        }
        if let Some(code) = &self.data().code {
            map.serialize_entry("code", code)?;
        }
        self.data().read_fields(map, reads)
    }

    fn deserialize_data<'de, D: Deserializer<'de>>(
        kind: &str,
        deserializer: D,
    ) -> Result<Self, D::Error> {
        let make = match Kind::parse(kind) {
            Some(Kind::CollectionGap) => GapFact::CollectionGap,
            Some(Kind::SourceResolutionGap) => GapFact::SourceResolutionGap,
            Some(Kind::DynamicImportLimit) => GapFact::DynamicImportLimit,
            Some(Kind::PrivateAttributeAccessLimit) => GapFact::PrivateAttributeAccessLimit,
            _ => match ExceptionName::parse(kind) {
                Some(exception) => {
                    let data = GapData::deserialize(deserializer)?;
                    return Ok(GapFact::ExceptionGap { exception, data });
                }
                None => {
                    return Err(D::Error::custom(format!(
                        "the kind {kind} is not a gap kind"
                    )))
                }
            },
        };
        GapData::deserialize(deserializer).map(make)
    }

    fn variants(generator: &mut SchemaGenerator) -> Vec<(Value, Schema)> {
        let data = generator.subschema_for::<GapData>();
        let mut variants: Vec<(Value, Schema)> = [
            Kind::CollectionGap,
            Kind::SourceResolutionGap,
            Kind::DynamicImportLimit,
            Kind::PrivateAttributeAccessLimit,
        ]
        .iter()
        .map(|kind| (json!({"const": kind.as_str()}), data.clone()))
        .collect();
        let names: Vec<&str> = ExceptionName::ALL
            .iter()
            .map(|name| name.as_str())
            .collect();
        variants.push((json!({"enum": names}), data));
        variants
    }
}

/// One section of a reply: its name and its records.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "name", content = "records", rename_all = "snake_case")]
pub enum Section {
    Imports(Vec<Record<ImportFact>>),
    Symbols(Vec<Record<SymbolFact>>),
    Calls(Vec<Record<CallFact>>),
    References(Vec<Record<ReferenceFact>>),
    Bindings(Vec<Record<BindingFact>>),
    Constructs(Vec<Record<ConstructFact>>),
    TypingSignals(Vec<Record<SignalFact>>),
    Unknowns(Vec<Record<GapFact>>),
}

impl Section {
    /// The name of the section on the wire.
    pub fn name(&self) -> &'static str {
        match self {
            Section::Imports(_) => "imports",
            Section::Symbols(_) => "symbols",
            Section::Calls(_) => "calls",
            Section::References(_) => "references",
            Section::Bindings(_) => "bindings",
            Section::Constructs(_) => "constructs",
            Section::TypingSignals(_) => "typing_signals",
            Section::Unknowns(_) => "unknowns",
        }
    }
}

impl Section {
    /// The count of records.
    pub fn len(&self) -> usize {
        match self {
            Section::Imports(records) => records.len(),
            Section::Symbols(records) => records.len(),
            Section::Calls(records) => records.len(),
            Section::References(records) => records.len(),
            Section::Bindings(records) => records.len(),
            Section::Constructs(records) => records.len(),
            Section::TypingSignals(records) => records.len(),
            Section::Unknowns(records) => records.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl ReadSet for Section {
    fn read_set_entries<M: SerializeMap>(&self, map: &mut M) -> Result<(), M::Error> {
        map.serialize_entry("name", self.name())?;
        match self {
            Section::Imports(records) => map.serialize_entry("records", &readset::List(records)),
            Section::Symbols(records) => map.serialize_entry("records", &readset::List(records)),
            Section::Calls(records) => map.serialize_entry("records", &readset::List(records)),
            Section::References(records) => map.serialize_entry("records", &readset::List(records)),
            Section::Bindings(records) => map.serialize_entry("records", &readset::List(records)),
            Section::Constructs(records) => map.serialize_entry("records", &readset::List(records)),
            Section::TypingSignals(records) => {
                map.serialize_entry("records", &readset::List(records))
            }
            Section::Unknowns(records) => map.serialize_entry("records", &readset::List(records)),
        }
    }
}

#[cfg(test)]
#[path = "sections_tests.rs"]
mod tests;
