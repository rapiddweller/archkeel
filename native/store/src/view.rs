// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed fields that the generic validation reads from one record (AD-346).
//!
//! The data types of `archkeel-facts` differ per kind, and the Python checks read a field by its
//! name across kinds (`source_module`, `owner`, ...). `View` is that cross-kind reading, typed.
//! `View::of` gets it through JSON: it writes the typed record to JSON bytes and reads them back
//! into `View`, one record at a time. This is the third JSON edge of the store. The follow-up is a
//! typed field-access trait on the data types of `archkeel-facts`, which removes this round trip.

use archkeel_facts::nested::{AttributeDeclaration, BaseDeclaration, MemberInventory};
use archkeel_facts::vocab::{EvidenceClass, Status};
use archkeel_facts::{FactData, Record};
use serde::de::IgnoredAny;
use serde::{Deserialize, Deserializer};

/// A field that can be absent, `null` or a value: `None`, `Some(None)` or `Some(Some(value))`.
fn present<'de, D: Deserializer<'de>, T: Deserialize<'de>>(
    deserializer: D,
) -> Result<Option<T>, D::Error> {
    T::deserialize(deserializer).map(Some)
}

#[derive(Debug, Default, Deserialize)]
#[serde(default)]
pub(crate) struct Data {
    #[serde(deserialize_with = "present")]
    pub(crate) source_module: Option<Option<String>>,
    #[serde(deserialize_with = "present")]
    pub(crate) module: Option<Option<String>>,
    pub(crate) owner: Option<String>,
    pub(crate) source_scope: Option<String>,
    pub(crate) qualified_name: Option<String>,
    pub(crate) declaration_scope: Option<String>,
    pub(crate) source_package: Option<String>,
    pub(crate) target_module: Option<String>,
    pub(crate) target_package: Option<String>,
    pub(crate) construct: Option<String>,
    pub(crate) source_file: Option<String>,
    pub(crate) expression: Option<String>,
    pub(crate) status: Option<Status>,
    pub(crate) targets: Option<Vec<String>>,
    pub(crate) resolution_dimension: Option<String>,
    pub(crate) file: Option<String>,
    pub(crate) lexical_parent_id: Option<String>,
    pub(crate) base_declarations: Option<Vec<BaseDeclaration>>,
    pub(crate) member_inventories: Option<Vec<MemberInventory>>,
    pub(crate) attribute_declarations: Option<Vec<AttributeDeclaration>>,
    call_binding: Option<IgnoredAny>,
    call_arguments: Option<IgnoredAny>,
    guarded_effect: Option<IgnoredAny>,
    contextmanager_signature: Option<IgnoredAny>,
    guard_boolean_members: Option<IgnoredAny>,
    local_source_binding: Option<IgnoredAny>,
    declaration_definition_id: Option<IgnoredAny>,
    instance_member_scope_evidence_id: Option<IgnoredAny>,
    receiver_binding: Option<IgnoredAny>,
}

impl Data {
    /// The fields whose proof is a Python check that the store does not port yet.
    pub(crate) fn unchecked(&self) -> Option<&'static str> {
        [
            (self.call_binding.is_some(), "call_binding"),
            (self.call_arguments.is_some(), "call_arguments"),
            (self.guarded_effect.is_some(), "guarded_effect"),
            (
                self.contextmanager_signature.is_some(),
                "contextmanager_signature",
            ),
            (
                self.guard_boolean_members.is_some(),
                "guard_boolean_members",
            ),
            (self.local_source_binding.is_some(), "local_source_binding"),
            (self.declaration_scope.is_some(), "declaration_scope"),
            (
                self.declaration_definition_id.is_some(),
                "declaration_definition_id",
            ),
            (
                self.instance_member_scope_evidence_id.is_some(),
                "instance_member_scope_evidence_id",
            ),
            (self.receiver_binding.is_some(), "receiver_binding"),
        ]
        .into_iter()
        .find_map(|(present, name)| present.then_some(name))
    }
}

#[derive(Debug, Deserialize)]
pub(crate) struct View {
    pub(crate) id: String,
    pub(crate) evidence_class: EvidenceClass,
    pub(crate) kind: String,
    pub(crate) subjects: Vec<String>,
    pub(crate) evidence_ids: Vec<String>,
    pub(crate) fact_ids: Vec<String>,
    pub(crate) data: Data,
}

impl View {
    pub(crate) fn of<D: FactData>(record: &Record<D>) -> Result<View, String> {
        let bytes = serde_json::to_vec(record).map_err(|error| error.to_string())?;
        serde_json::from_slice(&bytes).map_err(|error| error.to_string())
    }
}
