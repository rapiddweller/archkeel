// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed ids and the tables that give them out. An id is an index into one table only: a
//! `ModuleId` can never index the components.

use std::marker::PhantomData;

/// An id of one table. Only `Table::push` makes an id.
pub trait Id: Copy + Eq + Ord + std::hash::Hash + std::fmt::Debug {
    /// The index of the row in its table.
    fn index(self) -> usize;
    #[doc(hidden)]
    fn from_index(index: u32) -> Self;
}

macro_rules! id_type {
    ($(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
        pub struct $name(u32);

        impl Id for $name {
            fn index(self) -> usize {
                self.0 as usize
            }

            fn from_index(index: u32) -> Self {
                $name(index)
            }
        }
    };
}

id_type!(
    /// The id of a module of the reply (slice S1 fills the table).
    ModuleId
);
id_type!(
    /// The id of a package of the reply (slice S1 fills the table).
    PackageId
);
id_type!(
    /// The id of a component of the contract.
    ComponentId
);

/// The rows of one kind, indexed by their id.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Table<I, T> {
    rows: Vec<T>,
    id: PhantomData<fn() -> I>,
}

impl<I: Id, T> Table<I, T> {
    /// A table of these rows, or `None` when an id cannot hold their number (`u32`).
    pub(crate) fn of_rows(rows: Vec<T>) -> Option<Table<I, T>> {
        u32::try_from(rows.len()).ok()?;
        Some(Table {
            rows,
            id: PhantomData,
        })
    }

    /// The row of an id.
    pub fn get(&self, id: I) -> Option<&T> {
        self.rows.get(id.index())
    }

    /// The number of rows.
    pub fn len(&self) -> usize {
        self.rows.len()
    }

    /// True when the table has no row.
    pub fn is_empty(&self) -> bool {
        self.rows.is_empty()
    }

    /// Each id with its row, in the order of `push`.
    pub fn iter(&self) -> impl Iterator<Item = (I, &T)> {
        self.rows
            .iter()
            .zip(0u32..)
            .map(|(row, index)| (I::from_index(index), row))
    }
}
