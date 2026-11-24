// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module that registers the type in a registry outside the workspace (hole H2).

pub fn put() {
    regdep::register(crate::h2_b::X);
}
