// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The read-set: the second JSON form of the same types.
//!
//! A record keeps `id`, `kind`, `area`, `subjects` and `evidence_ids`. Its data keeps only the
//! fields that a rule or a view reads for its area and kind (WP1 of issue #880, `readset_fields`).
//! A read field is written as the wire writes it: a `null` stays `null`, and a field that the wire
//! skips is skipped. An analyzer failure adds its exception name, and a gap adds its reason code.
//!
//! Measured on this crate: the 21 980 x35 import records are 15.5 MB on the wire and 10.0 MB in
//! the read-set; the 156 808 section records of the WP1 replies are 128.7 MB and 91.9 MB. The data
//! of each record equals the WP1 read-set; the shared fields and the ids hold most of the bytes.

use serde::ser::{SerializeMap, SerializeSeq, Serializer};
use serde::Serialize;

/// A value that has a read-set form: a JSON object with the read fields.
pub trait ReadSet {
    /// Write the read fields into an open map.
    fn read_set_entries<M: SerializeMap>(&self, map: &mut M) -> Result<(), M::Error>;
}

/// The read data fields of one area and kind (`readset_fields::fields`), or `None` when WP1 has
/// no list for the kind.
pub type Reads = Option<&'static [&'static str]>;

/// Whether the read-set writes the field `name`. Without a list, each `read` field is written.
pub fn allowed(reads: Reads, name: &str) -> bool {
    reads.is_none_or(|fields| fields.binary_search(&name).is_ok())
}

/// The data of a record kind: it writes its read fields into an open map.
pub trait ReadFields {
    fn read_fields<M: SerializeMap>(&self, map: &mut M, reads: Reads) -> Result<(), M::Error>;
}

/// A field that the wire can skip. The read-set skips it when the wire does.
pub trait Present {
    fn present(&self) -> bool;
}

/// Whether the wire omits a skippable field: the `serde` test of each `skip` field.
pub(crate) fn omitted<T: Present>(value: &T) -> bool {
    !value.present()
}

impl<T> Present for Option<T> {
    fn present(&self) -> bool {
        self.is_some()
    }
}

impl<T> Present for crate::nullable::Nullable<T> {
    fn present(&self) -> bool {
        !self.is_absent()
    }
}

/// The read-set form of one value.
pub struct Of<'a, T: ?Sized>(pub &'a T);

impl<T: ReadSet + ?Sized> Serialize for Of<'_, T> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(None)?;
        self.0.read_set_entries(&mut map)?;
        map.end()
    }
}

/// The read-set form of a list.
pub struct List<'a, T>(pub &'a [T]);

impl<T: ReadSet> Serialize for List<'_, T> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut seq = serializer.serialize_seq(Some(self.0.len()))?;
        for item in self.0 {
            seq.serialize_element(&Of(item))?;
        }
        seq.end()
    }
}

/// The read-set JSON of `value`.
pub fn to_vec<T: ReadSet + ?Sized>(value: &T) -> serde_json::Result<Vec<u8>> {
    serde_json::to_vec(&Of(value))
}
