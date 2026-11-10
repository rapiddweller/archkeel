// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One source record: the fields that every section shares, and the typed data of its kind.
//!
//! The kind and the data are one value (`FactData`), so a record cannot hold the data of another
//! kind. The wire writes the keys of protocol 9 in this order: `id`, `evidence_class`, `area`,
//! `kind`, `title`, `subjects`, `evidence_ids`, `rule_ids`, `fact_ids`, `provenance`, `data`.
//! `rule_ids` and `provenance` are always empty for a source record, and a decode rejects a
//! value in them.

use std::fmt;
use std::marker::PhantomData;

use schemars::{json_schema, JsonSchema, Schema, SchemaGenerator};
use serde::de::{self, DeserializeSeed, IgnoredAny, MapAccess, Visitor};
use serde::ser::{SerializeMap, Serializer};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{json, Value};

use crate::ids::{EvidenceId, FactId};
use crate::readset::ReadSet;
use crate::vocab::{Area, EvidenceClass, Kind};

/// The kind and the data of the records of one section.
pub trait FactData: Sized {
    /// The name of the type in the schema.
    const NAME: &'static str;

    /// The closed kind of the record.
    fn kind(&self) -> Kind;

    /// The kind as protocol 9 writes it. Only an analyzer failure differs from `kind`.
    fn wire_kind(&self) -> &str;

    /// Write the data in the wire form.
    fn serialize_data<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error>;

    /// Write the read-set fields of the data into an open map.
    fn read_set_entries<M: SerializeMap>(&self, map: &mut M) -> Result<(), M::Error>;

    /// Read the data of the record that has the protocol 9 kind `kind`.
    fn deserialize_data<'de, D: Deserializer<'de>>(
        kind: &str,
        deserializer: D,
    ) -> Result<Self, D::Error>;

    /// The schema of the kind text and of the data, for each kind of the section.
    fn variants(generator: &mut SchemaGenerator) -> Vec<(Value, Schema)>;
}

#[derive(Clone, Debug, PartialEq)]
pub struct Record<D> {
    pub id: FactId,
    pub evidence_class: EvidenceClass,
    pub area: Area,
    pub title: String,
    /// Sorted, as `classified` sorts them.
    pub subjects: Vec<String>,
    /// Sorted, as `classified` sorts them.
    pub evidence_ids: Vec<EvidenceId>,
    /// In the order of the producer: the Python collector does not sort them.
    pub fact_ids: Vec<FactId>,
    pub data: D,
}

impl<D: FactData> Record<D> {
    pub fn kind(&self) -> Kind {
        self.data.kind()
    }
}

/// The data of a record in the wire form.
struct Data<'a, D>(&'a D);

impl<D: FactData> Serialize for Data<'_, D> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0.serialize_data(serializer)
    }
}

/// The data of a record in the read-set form.
struct ReadSetData<'a, D>(&'a D);

impl<D: FactData> Serialize for ReadSetData<'_, D> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(None)?;
        self.0.read_set_entries(&mut map)?;
        map.end()
    }
}

const EMPTY: [(); 0] = [];

impl<D: FactData> Serialize for Record<D> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(Some(11))?;
        map.serialize_entry("id", &self.id)?;
        map.serialize_entry("evidence_class", &self.evidence_class)?;
        map.serialize_entry("area", &self.area)?;
        map.serialize_entry("kind", self.data.wire_kind())?;
        map.serialize_entry("title", &self.title)?;
        map.serialize_entry("subjects", &self.subjects)?;
        map.serialize_entry("evidence_ids", &self.evidence_ids)?;
        map.serialize_entry("rule_ids", &EMPTY)?;
        map.serialize_entry("fact_ids", &self.fact_ids)?;
        map.serialize_entry("provenance", &EMPTY)?;
        map.serialize_entry("data", &Data(&self.data))?;
        map.end()
    }
}

/// The read-set of a record: `id`, `kind`, `area`, `subjects`, `evidence_ids` and the read data.
/// `kind` is the closed kind; an analyzer failure carries its exception name in the data.
impl<D: FactData> ReadSet for Record<D> {
    fn read_set_entries<M: SerializeMap>(&self, map: &mut M) -> Result<(), M::Error> {
        map.serialize_entry("id", &self.id)?;
        map.serialize_entry("kind", &self.data.kind())?;
        map.serialize_entry("area", &self.area)?;
        map.serialize_entry("subjects", &self.subjects)?;
        map.serialize_entry("evidence_ids", &self.evidence_ids)?;
        map.serialize_entry("data", &ReadSetData(&self.data))
    }
}

/// Reads the data when the kind is known; the wire of the native collectors writes `kind` first.
struct DataSeed<'k, D> {
    kind: &'k str,
    data: PhantomData<D>,
}

impl<'de, D: FactData> DeserializeSeed<'de> for DataSeed<'_, D> {
    type Value = D;

    fn deserialize<De: Deserializer<'de>>(self, deserializer: De) -> Result<D, De::Error> {
        D::deserialize_data(self.kind, deserializer)
    }
}

/// An empty list: `rule_ids` and `provenance` of a source record.
fn empty<'de, A: MapAccess<'de>>(map: &mut A, key: &str) -> Result<(), A::Error> {
    let items: Vec<IgnoredAny> = map.next_value()?;
    if items.is_empty() {
        Ok(())
    } else {
        Err(de::Error::custom(format!("a source record has no {key}")))
    }
}

struct Fields<D> {
    id: Option<FactId>,
    evidence_class: Option<EvidenceClass>,
    area: Option<Area>,
    kind: Option<String>,
    title: Option<String>,
    subjects: Option<Vec<String>>,
    evidence_ids: Option<Vec<EvidenceId>>,
    fact_ids: Option<Vec<FactId>>,
    data: Option<D>,
    /// The data of a reply that writes `data` before `kind`, such as the sorted Python reply.
    early: Option<Value>,
}

fn missing<T, E: de::Error>(value: Option<T>, name: &'static str) -> Result<T, E> {
    value.ok_or_else(|| de::Error::missing_field(name))
}

impl<D: FactData> Fields<D> {
    fn record<E: de::Error>(self) -> Result<Record<D>, E> {
        let kind = missing(self.kind, "kind")?;
        let data = match (self.data, self.early) {
            (Some(data), _) => data,
            (None, Some(early)) => D::deserialize_data(&kind, early).map_err(E::custom)?,
            (None, None) => return Err(de::Error::missing_field("data")),
        };
        Ok(Record {
            id: missing(self.id, "id")?,
            evidence_class: missing(self.evidence_class, "evidence_class")?,
            area: missing(self.area, "area")?,
            title: missing(self.title, "title")?,
            subjects: missing(self.subjects, "subjects")?,
            evidence_ids: missing(self.evidence_ids, "evidence_ids")?,
            fact_ids: missing(self.fact_ids, "fact_ids")?,
            data,
        })
    }
}

struct RecordVisitor<D>(PhantomData<D>);

/// The keys of a record, read without a copy of the key text.
#[derive(Deserialize)]
#[serde(field_identifier, rename_all = "snake_case")]
enum Key {
    Id,
    EvidenceClass,
    Area,
    Kind,
    Title,
    Subjects,
    EvidenceIds,
    RuleIds,
    FactIds,
    Provenance,
    Data,
}

const FIELDS: &[&str] = &[
    "id",
    "evidence_class",
    "area",
    "kind",
    "title",
    "subjects",
    "evidence_ids",
    "rule_ids",
    "fact_ids",
    "provenance",
    "data",
];

fn set<T, E: de::Error>(slot: &mut Option<T>, value: T, name: &'static str) -> Result<(), E> {
    if slot.replace(value).is_some() {
        return Err(de::Error::duplicate_field(name));
    }
    Ok(())
}

impl<'de, D: FactData> Visitor<'de> for RecordVisitor<D> {
    type Value = Record<D>;

    fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        formatter.write_str("a source record")
    }

    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Record<D>, A::Error> {
        let mut fields = Fields::<D> {
            id: None,
            evidence_class: None,
            area: None,
            kind: None,
            title: None,
            subjects: None,
            evidence_ids: None,
            fact_ids: None,
            data: None,
            early: None,
        };
        while let Some(key) = map.next_key::<Key>()? {
            match key {
                Key::Id => set(&mut fields.id, map.next_value()?, "id")?,
                Key::EvidenceClass => {
                    set(
                        &mut fields.evidence_class,
                        map.next_value()?,
                        "evidence_class",
                    )?;
                }
                Key::Area => set(&mut fields.area, map.next_value()?, "area")?,
                Key::Kind => set(&mut fields.kind, map.next_value()?, "kind")?,
                Key::Title => set(&mut fields.title, map.next_value()?, "title")?,
                Key::Subjects => set(&mut fields.subjects, map.next_value()?, "subjects")?,
                Key::EvidenceIds => {
                    set(&mut fields.evidence_ids, map.next_value()?, "evidence_ids")?;
                }
                Key::FactIds => set(&mut fields.fact_ids, map.next_value()?, "fact_ids")?,
                Key::RuleIds => empty(&mut map, "rule_ids")?,
                Key::Provenance => empty(&mut map, "provenance")?,
                Key::Data => match fields.kind.as_deref() {
                    Some(kind) => {
                        let seed = DataSeed::<D> {
                            kind,
                            data: PhantomData,
                        };
                        set(&mut fields.data, map.next_value_seed(seed)?, "data")?;
                    }
                    None => set(&mut fields.early, map.next_value()?, "data")?,
                },
            }
        }
        fields.record()
    }
}

impl<'de, D: FactData> Deserialize<'de> for Record<D> {
    fn deserialize<De: Deserializer<'de>>(deserializer: De) -> Result<Self, De::Error> {
        deserializer.deserialize_struct("Record", FIELDS, RecordVisitor(PhantomData))
    }
}

impl<D: FactData> JsonSchema for Record<D> {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        format!("Record_{}", D::NAME).into()
    }

    fn json_schema(generator: &mut SchemaGenerator) -> Schema {
        let kinds: Vec<Value> = D::variants(generator)
            .into_iter()
            .map(|(kind, data)| {
                json!({"properties": {"kind": kind, "data": data}, "required": ["kind", "data"]})
            })
            .collect();
        let empty = json!({"type": "array", "maxItems": 0});
        json_schema!({
            "type": "object",
            "properties": {
                "id": generator.subschema_for::<FactId>(),
                "evidence_class": generator.subschema_for::<EvidenceClass>(),
                "area": generator.subschema_for::<Area>(),
                "kind": {"type": "string"},
                "title": {"type": "string"},
                "subjects": {"type": "array", "items": {"type": "string"}},
                "evidence_ids": generator.subschema_for::<Vec<EvidenceId>>(),
                "rule_ids": empty,
                "fact_ids": generator.subschema_for::<Vec<FactId>>(),
                "provenance": empty,
                "data": {"type": "object"},
            },
            "required": FIELDS,
            "additionalProperties": false,
            "oneOf": kinds,
        })
    }
}

#[cfg(test)]
#[path = "record_tests.rs"]
mod tests;
