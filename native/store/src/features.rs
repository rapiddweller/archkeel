// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The resolution features that more than one check of the store reads (a leaf: no check of the
//! store may be imported here, so the checks do not form a cycle).

/// The feature of the Python survey that writes the symbol and the route of each named import
/// (AD-504).
pub(crate) const ROUTES_FEATURE: &str = "import-routes-v1";
