// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed fields that the generic validation reads from one record (AD-346).
//!
//! The data types of `archkeel-facts` differ per kind, and the Python checks read a field by its
//! name across kinds (`source_module`, `owner`, ...). `View` borrows the shared fields of a typed
//! record and its `Fields` (`archkeel_facts::fields`). No JSON is written or read.

use archkeel_facts::fields::Fields;
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::EvidenceClass;
use archkeel_facts::{FactData, Record};

pub(crate) struct View<'a> {
    pub(crate) id: &'a str,
    pub(crate) evidence_class: EvidenceClass,
    /// The kind as the wire writes it: an analyzer failure keeps its exception name.
    pub(crate) kind: &'a str,
    pub(crate) subjects: &'a [String],
    pub(crate) evidence_ids: &'a [EvidenceId],
    pub(crate) fact_ids: &'a [FactId],
    pub(crate) data: Fields<'a>,
}

impl<'a> View<'a> {
    pub(crate) fn new<D: FactData>(record: &'a Record<D>) -> Self {
        View {
            id: record.id.as_str(),
            evidence_class: record.evidence_class,
            kind: record.data.wire_kind(),
            subjects: &record.subjects,
            evidence_ids: &record.evidence_ids,
            fact_ids: &record.fact_ids,
            data: record.data.fields(),
        }
    }

    /// The fields whose proof is a Python check that the store does not port yet.
    pub(crate) fn unchecked(&self) -> Option<&'static str> {
        let data = &self.data;
        [
            (data.call_binding, "call_binding"),
            (data.call_arguments, "call_arguments"),
            (data.guarded_effect, "guarded_effect"),
            (data.contextmanager_signature, "contextmanager_signature"),
            (data.guard_boolean_members, "guard_boolean_members"),
            (data.local_source_binding, "local_source_binding"),
            (data.declaration_scope.is_some(), "declaration_scope"),
            (data.declaration_definition_id, "declaration_definition_id"),
            (
                data.instance_member_scope_evidence_id,
                "instance_member_scope_evidence_id",
            ),
            (data.receiver_binding, "receiver_binding"),
        ]
        .into_iter()
        .find_map(|(present, name)| present.then_some(name))
    }
}
