// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The read-set: the second JSON form of the same types.
//!
//! It holds only the fields that a rule or a view reads (WP1 of issue #880, `readset_classes`).
//! A read field is written as the wire writes it: a `null` stays `null`, and a field that the wire
//! skips is skipped. Most skipped fields belong to another producer of the same kind.
//! On the x35 tree the read-set of all sections is 46.8 MB instead of 278 MB (WP2).

use serde::ser::{SerializeMap, SerializeSeq, Serializer};
use serde::Serialize;

/// A value that has a read-set form: a JSON object with the read fields.
pub trait ReadSet {
    /// Write the read fields into an open map.
    fn read_set_entries<M: SerializeMap>(&self, map: &mut M) -> Result<(), M::Error>;
}

/// A field that the wire can skip. The read-set skips it when the wire does.
pub trait Present {
    fn present(&self) -> bool;
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
