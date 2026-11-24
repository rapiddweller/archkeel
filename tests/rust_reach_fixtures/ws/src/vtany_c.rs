// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `vtany`: the vendored crate is under the root and is no member.

pub fn make() -> Box<dyn std::any::Any> {
    vdep::erase_any(crate::vtany_b::X)
}
