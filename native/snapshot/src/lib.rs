// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one owner of how a native collector reads a snapshot.
//!
//! It owns the POSIX path text, the contained read, the symlink rule, the size limit and the
//! digest of each input. A collector adds no read of its own. Language rules, such as which
//! directory holds installed packages, stay in the collector.

#![forbid(unsafe_code)]
// A public item that no other crate can reach is a lie in a library.
#![deny(unreachable_pub)]

mod nesting;
pub mod paths;
mod snapshot;
pub mod work;
// The temporary tree of the unit tests. A test of another crate enables the `test-tree` feature.
#[cfg(any(test, feature = "test-tree"))]
#[allow(
    clippy::unwrap_used,
    reason = "a failed set-up fails the test that uses the tree"
)]
pub mod test_tree;

pub use nesting::block_comment_end;
pub use snapshot::listing::{Entry, RootCheck};
pub use snapshot::{Hidden, Snapshot, MAX_FILE_BYTES};
