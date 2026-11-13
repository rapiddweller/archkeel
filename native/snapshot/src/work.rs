// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A conservative parse-work charge before any in-process collector sees bytes (AD-420).

use std::collections::HashMap;
use std::sync::{LazyLock, Mutex, MutexGuard};
use std::thread::{self, ThreadId};

/// The most charged work in one file. Each byte costs one plus all possible tokens before it.
pub const MAX_PARSE_WORK: u64 = 1 << 30;
/// The most bytes returned by all snapshot reads in one in-process collection.
pub const MAX_SCAN_BYTES: u64 = 64 << 20;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WorkScope {
    File,
    Scan,
}

/// A file that the in-process collector must not parse.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkLimit {
    pub path: String,
    pub scope: WorkScope,
}

impl std::fmt::Display for WorkLimit {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if self.scope == WorkScope::Scan {
            return write!(
                out,
                "parse_work_limit: scan input exceeds {MAX_SCAN_BYTES} bytes at {}",
                self.path
            );
        }
        write!(
            out,
            "parse_work_limit: {} exceeds {MAX_PARSE_WORK} charged units",
            self.path
        )
    }
}

// Keep thread-owned budgets in ordinary code that the self-collector can read, not macro tokens.
static LIMITS: LazyLock<Mutex<HashMap<ThreadId, Budget>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn limits() -> MutexGuard<'static, HashMap<ThreadId, Budget>> {
    LIMITS
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

struct Budget {
    remaining: u64,
    hit: Option<WorkLimit>,
}

#[cfg(any(test, feature = "test-tree"))]
pub(crate) fn charged_bytes() -> Option<u64> {
    limits()
        .get(&thread::current().id())
        .map(|budget| MAX_SCAN_BYTES - budget.remaining)
}

/// Bound every snapshot read on this thread. A hit discards the whole result, including facts
/// that the collector made before the hit. The binary collector keeps its existing host limit.
pub fn bounded<T>(work: impl FnOnce() -> T) -> Result<T, WorkLimit> {
    struct Restore(bool);
    impl Drop for Restore {
        fn drop(&mut self) {
            if self.0 {
                limits().remove(&thread::current().id());
            }
        }
    }
    let restore = Restore({
        let mut limits = limits();
        let entry = limits.entry(thread::current().id());
        let owned = matches!(entry, std::collections::hash_map::Entry::Vacant(_));
        entry.or_insert(Budget {
            remaining: MAX_SCAN_BYTES,
            hit: None,
        });
        owned
    });
    let result = work();
    let hit = limits()
        .get(&thread::current().id())
        .and_then(|budget| budget.hit.clone());
    drop(restore);
    match hit {
        Some(hit) => Err(hit),
        None => Ok(result),
    }
}

pub(crate) fn permits(path: &str, bytes: &[u8]) -> bool {
    let mut limits = limits();
    let Some(budget) = limits.get_mut(&thread::current().id()) else {
        return true;
    };
    if budget.hit.is_some() {
        return false;
    }
    let scope = if over(bytes) {
        Some(WorkScope::File)
    } else if bytes.len() as u64 > budget.remaining {
        Some(WorkScope::Scan)
    } else {
        None
    };
    if let Some(scope) = scope {
        budget.hit = Some(WorkLimit {
            path: path.to_owned(),
            scope,
        });
        return false;
    }
    budget.remaining -= bytes.len() as u64;
    true
}

/// Word runs count once; punctuation and non-ASCII bytes count individually. Quotes, comments
/// and closing brackets never reduce the charge. No language lexer can hide nesting from it.
fn over(bytes: &[u8]) -> bool {
    exceeds(bytes, MAX_PARSE_WORK)
}

fn exceeds(bytes: &[u8], budget: u64) -> bool {
    let (mut tokens, mut charge, mut word) = (0_u64, 0_u64, false);
    for &byte in bytes {
        let next_word = byte.is_ascii_alphanumeric() || byte == b'_';
        if !(byte.is_ascii_whitespace() || word && next_word) {
            tokens += 1;
        }
        word = next_word;
        charge += 1 + tokens;
        if charge > budget {
            return true;
        }
    }
    false
}

#[cfg(test)]
#[path = "work_tests.rs"]
mod tests;
