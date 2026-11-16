// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Code` cell of the payload and the trait of the closed list that it indexes.

use std::cmp::Ordering;
use std::fmt;
use std::marker::PhantomData;

use serde::{Deserialize, Deserializer, Serialize, Serializer};

/// One closed code list of the schema.
pub trait CodeList: Copy + 'static {
    /// The name of the list in `$defs` of the schema.
    const NAME: &'static str;
    /// The values, in code order.
    const VALUES: &'static [Self];
    /// The text of each value, in code order (`x-codes`).
    const TEXTS: &'static [&'static str];
    /// The code of this value.
    fn code(self) -> u32;
}

/// A code of the list `L`, as the payload holds it.
pub struct Code<L> {
    value: u32,
    list: PhantomData<L>,
}

impl<L: CodeList> Code<L> {
    /// The code of one value of the list.
    pub fn of(value: L) -> Code<L> {
        Code::raw(value.code())
    }

    /// A code as read from a payload; it can lie beyond the list.
    pub fn raw(value: u32) -> Code<L> {
        Code {
            value,
            list: PhantomData,
        }
    }

    /// The number of the code.
    pub fn value(self) -> u32 {
        self.value
    }

    /// The value of the list, or `None` for a code beyond the list of this crate.
    pub fn known(self) -> Option<L> {
        usize::try_from(self.value)
            .ok()
            .and_then(|index| L::VALUES.get(index).copied())
    }

    /// True when the code is this value.
    pub fn is(self, value: L) -> bool {
        self.value == value.code()
    }
}

impl<L> Clone for Code<L> {
    fn clone(&self) -> Self {
        *self
    }
}

impl<L> Copy for Code<L> {}

impl<L> PartialEq for Code<L> {
    fn eq(&self, other: &Self) -> bool {
        self.value == other.value
    }
}

impl<L> Eq for Code<L> {}

impl<L> PartialOrd for Code<L> {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl<L> Ord for Code<L> {
    fn cmp(&self, other: &Self) -> Ordering {
        self.value.cmp(&other.value)
    }
}

impl<L: CodeList> fmt::Debug for Code<L> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let text = usize::try_from(self.value)
            .ok()
            .and_then(|index| L::TEXTS.get(index));
        match text {
            Some(text) => write!(formatter, "{}:{text}", L::NAME),
            None => write!(formatter, "{}:{}?", L::NAME, self.value),
        }
    }
}

impl<L> Serialize for Code<L> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_u32(self.value)
    }
}

impl<'de, L> Deserialize<'de> for Code<L> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        Ok(Code {
            value: u32::deserialize(deserializer)?,
            list: PhantomData,
        })
    }
}
