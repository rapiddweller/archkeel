// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Report` request: the report v2 payload. Slice 0d writes it here.

use archkeel_model::{Reason, Unsupported};

pub(crate) fn answer() -> Reason {
    Reason::Unsupported(Unsupported::Report)
}
