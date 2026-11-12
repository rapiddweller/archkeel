// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The brand of one `Model::scope` call (AD-363): the scope and each proof of slice S7 carry it.

use std::marker::PhantomData;

/// An invariant lifetime: two calls of `Model::scope` never have the same one.
pub(crate) type Brand<'id> = PhantomData<fn(&'id ()) -> &'id ()>;
