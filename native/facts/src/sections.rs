// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sections of a reply and the kinds that each section holds.
//!
//! The section decides the data type of a kind: `dynamic_import` is an import in `imports` and a
//! typing signal in `typing_signals`. A kind that its section does not hold is a decode error.

use schemars::{JsonSchema, Schema, SchemaGenerator};
use serde::de::Error as _;
use serde::ser::Serializer;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{json, Value};

use crate::data::{
    BindingData, CallData, CallableData, ClassData, ConstructData, GapData, ImportData,
    NumericOperandData, PlaceholderData, PlainConstructData, ReferenceData, SelectorData,
    SignalData, SourceRoleData, UnusedBindingData, ValueData,
};
use crate::record::{FactData, Record};
use crate::vocab::{ExceptionName, Kind};

/// The data of a section: it gives the section that holds its records.
pub trait IntoSection: FactData {
    /// Wraps the records into the section that holds this data.
    fn section(records: Vec<Record<Self>>) -> Section;

    /// The name of the section on the wire.
    fn section_name() -> &'static str {
        Self::section(Vec::new()).name()
    }

    /// The records of `section`, when it is the section of this data.
    fn records(section: &Section) -> Option<&[Record<Self>]>;
}

/// The common typed payload of each kind of a section whose kinds share one data type. A trait
/// declared here, so the impl that `section_facts!` writes in this module is anchored here
/// (AD-662).
pub trait CommonData {
    /// The data type of every kind.
    type Data;

    /// The payload of this kind.
    fn data(&self) -> &Self::Data;
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
    /// The kinds of the `imports` section.
    pub enum ImportFact in Imports {
        /// An import statement or imported name.
        Import(ImportData),
        /// An import that publishes the name again.
        Reexport(ImportData),
        /// A type-only import.
        ImportType(ImportData),
        /// An `import x = require()` form.
        ImportEquals(ImportData),
        /// A `require` call.
        Require(ImportData),
        /// An import whose target is computed at run time.
        DynamicImport(ImportData),
        /// A global that a script file binds.
        ScriptGlobal(ImportData),
        /// An import inside a macro body.
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

    /// The import data that the record holds, for an edit.
    pub fn data_mut(&mut self) -> &mut ImportData {
        import_data!(self)
    }
}

section_facts! {
    /// The kinds of the `symbols` section.
    pub enum SymbolFact in Symbols {
        /// A class symbol.
        Class(ClassData),
        /// A function symbol.
        Function(CallableData),
        /// A method symbol.
        Method(CallableData),
        /// A constant symbol.
        Constant(ValueData),
        /// A type alias symbol.
        TypeAlias(ValueData),
        /// A name binding.
        Binding(ValueData),
        /// An alias symbol.
        Alias(ValueData),
        /// A binding that is set at run time.
        DynamicBinding(ValueData),
        /// A constant with a value that is known statically.
        StaticConstant(ValueData),
        /// A macro symbol.
        Macro(ValueData),
    }
}

section_facts! {
    /// The kinds of the `calls` section.
    pub enum CallFact in Calls {
        /// The calls of one scope.
        Calls(CallData),
        /// A call.
        Call(CallData),
        /// A call with one proven target.
        ResolvedCall(CallData),
        /// A call with a target that is only partly proven.
        PartiallyResolvedCall(CallData),
        /// A call with no proven target.
        UnresolvedCall(CallData),
    }
}

section_facts! {
    /// The kinds of the `references` section.
    pub enum ReferenceFact in References {
        /// The references of one scope.
        References(ReferenceData),
        /// A reference to a name.
        Reference(ReferenceData),
        /// A write into the namespace of a script.
        ScriptNamespaceEffect(ReferenceData),
        /// A reference that reads a value.
        ValueReference(ReferenceData),
        /// A reference to an attribute.
        AttributeReference(ReferenceData),
        /// The role that a source value plays.
        SourceRole(SourceRoleData),
    }
}

section_facts! {
    /// The kinds of the `bindings` section.
    pub enum BindingFact in Bindings {
        /// The bindings of one scope.
        Bindings(BindingData),
        /// A parameter that nothing reads.
        UnusedParameter(UnusedBindingData),
        /// A local name that nothing reads.
        UnusedLocal(UnusedBindingData),
    }
}

section_facts! {
    /// The kinds of the `constructs` section.
    pub enum ConstructFact in Constructs {
        /// A comparison with a string literal.
        StringLiteralCompare(ConstructData),
        /// A broad exception handler.
        BroadExcept(ConstructData),
        /// A call of `getattr`.
        GetattrCall(ConstructData),
        /// A call of `hasattr`.
        HasattrCall(ConstructData),
        /// A call of `setattr`.
        SetattrCall(ConstructData),
        /// A call of `delattr`.
        DelattrCall(ConstructData),
        /// A call of `vars`.
        VarsCall(ConstructData),
        /// A selector on a receiver.
        ConstructSelector(SelectorData),
        /// A numeric operand with its proof.
        NumericOperand(NumericOperandData),
        /// An `assert` statement.
        AssertStatement(PlainConstructData),
        /// A function body that declares no implementation.
        PlaceholderBody(PlaceholderData),
        /// A use of `__dict__`.
        DunderDict(PlainConstructData),
    }
}

section_facts! {
    /// The kinds of the `typing_signals` section.
    pub enum SignalFact in TypingSignals with SignalData {
        /// An `Any` annotation.
        AnyAnnotation,
        /// A dict annotation with `Any` values.
        DictAnyAnnotation,
        /// A callable annotation with `Any`.
        CallableAnyAnnotation,
        /// An `object` annotation.
        ObjectAnnotation,
        /// A call of `cast`.
        CastCall,
        /// A call of `getattr`.
        GetattrCall,
        /// A call of `hasattr`.
        HasattrCall,
        /// A call of `eval`.
        EvalCall,
        /// A call of `exec`.
        ExecCall,
        /// An import whose target is computed at run time.
        DynamicImport,
        /// A `type: ignore` comment.
        TypeIgnore,
        /// A position that crosses a package with no annotation.
        MissingCrossPackageAnnotation,
    }
}

/// A gap of the coverage or of the `unknowns` section.
#[derive(Clone, Debug, PartialEq)]
pub enum GapFact {
    /// A gap of the collection: a file or a part that the collector does not read.
    CollectionGap(GapData),
    /// A gap of the resolution of a source name.
    SourceResolutionGap(GapData),
    /// A dynamic import that the collector cannot follow.
    DynamicImportLimit(GapData),
    /// An access to a private attribute that the collector cannot type.
    PrivateAttributeAccessLimit(GapData),
    /// An analyzer failure. Protocol 9 writes the exception class name as the kind.
    ExceptionGap {
        /// The class name of the failure.
        exception: ExceptionName,
        /// The data of the gap.
        data: GapData,
    },
}

impl GapFact {
    /// The free text that the collector wrote beside the reason, if any (AD-540). It is no part of
    /// the gap key. The name is unique so that no call of it reads as a call of another `data`.
    pub fn collector_message(&self) -> Option<String> {
        self.data().message.clone()
    }

    /// The data of the gap, whatever its kind (AD-546: the baseline key reads it).
    pub fn data(&self) -> &GapData {
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
            .filter(|name| name.in_v9())
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
    /// The import records.
    Imports(Vec<Record<ImportFact>>),
    /// The symbol records.
    Symbols(Vec<Record<SymbolFact>>),
    /// The call records.
    Calls(Vec<Record<CallFact>>),
    /// The reference records.
    References(Vec<Record<ReferenceFact>>),
    /// The binding records.
    Bindings(Vec<Record<BindingFact>>),
    /// The construct records.
    Constructs(Vec<Record<ConstructFact>>),
    /// The typing signal records.
    TypingSignals(Vec<Record<SignalFact>>),
    /// The gap records.
    Unknowns(Vec<Record<GapFact>>),
}

impl Section {
    /// The name of the section on the wire.
    /// The value invariants of each record of the section (`Record::invariants`). Each fact
    /// type reads its own section (`IntoSection::records`), so a new section must list its type.
    pub fn invariants(&self) -> Result<(), &'static str> {
        fn each<D: IntoSection>(section: &Section) -> Result<(), &'static str> {
            D::records(section)
                .unwrap_or_default()
                .iter()
                .try_for_each(Record::invariants)
        }
        type Check = fn(&Section) -> Result<(), &'static str>;
        let checks: [Check; 8] = [
            each::<ImportFact>,
            each::<SymbolFact>,
            each::<CallFact>,
            each::<ReferenceFact>,
            each::<BindingFact>,
            each::<ConstructFact>,
            each::<SignalFact>,
            each::<GapFact>,
        ];
        // Exhaustive on purpose: a new section fails to compile here until `checks` names it.
        match self {
            Section::Imports(_)
            | Section::Symbols(_)
            | Section::Calls(_)
            | Section::References(_)
            | Section::Bindings(_)
            | Section::Constructs(_)
            | Section::TypingSignals(_)
            | Section::Unknowns(_) => checks.iter().try_for_each(|check| check(self)),
        }
    }

    /// The name of the section.
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

    /// True when the section holds no record.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

#[cfg(test)]
#[path = "sections_tests.rs"]
mod tests;
