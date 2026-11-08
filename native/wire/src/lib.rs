// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The collector wire that every native Archkeel collector shares.
//!
//! The host stays the trust boundary: `facts_codec.decode_response` validates each reply.

#![forbid(unsafe_code)]

pub mod identity;
pub mod protocol;
pub mod reply;
pub mod request;
