// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed ids and the tables that give them out. An id is an index into one table only: a
//! `ModuleId` can never index the components.

use std::marker::PhantomData;

use self::sealed::Sealed;

/// The seal of `Id`: its module is private, so no other crate can implement `Id` or call
/// `from_index`.
pub(crate) mod sealed {
    pub trait Sealed {
        /// The id of an index. Only a table of this crate calls it.
        fn from_index(index: u32) -> Self;
    }
}

/// An id of one table. Only a `Table` of this crate gives out an id (`Table::iter`).
///
/// Another crate cannot make an id from a number:
///
/// ```compile_fail
/// use archkeel_model::ComponentId;
/// let forged = ComponentId::from_index(7);
/// ```
///
/// and cannot add an id type of its own:
///
/// ```compile_fail
/// #[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
/// struct Forged;
/// impl archkeel_model::Id for Forged {
///     fn index(self) -> usize { 0 }
/// }
/// ```
pub trait Id: Sealed + Copy + Eq + Ord + std::hash::Hash + std::fmt::Debug {
    /// The index of the row in its table.
    fn index(self) -> usize;
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
        }

        impl Sealed for $name {
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
