// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The generic owner of the case `cgen`: a closure of it calls the generic function with its type parameter.

use crate::api::Tr;

pub fn outer<T: Tr + Default>() {
    let call = || crate::cgen_g::inner::<T>();
    call();
}
