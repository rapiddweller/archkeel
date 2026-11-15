// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The test of a skippable field: the wire omits an `Option` or a `Nullable` that is absent.

/// A field that the wire can skip.
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
