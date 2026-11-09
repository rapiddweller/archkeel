// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The collector wire that every native Archkeel collector shares.
//!
//! The host stays the trust boundary: `facts_codec.decode_response` validates each reply.

#![forbid(unsafe_code)]
// AD-327: a public item that no other crate can reach is a lie in a library.
#![deny(unreachable_pub)]

pub mod identity;
pub mod protocol;
pub mod records;
pub mod reply;
pub mod request;
