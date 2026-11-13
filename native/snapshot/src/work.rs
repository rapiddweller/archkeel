// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A conservative parse-work charge before any in-process collector sees bytes (AD-420).

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex, MutexGuard};
use std::thread::{self, ThreadId};

/// One unit per byte plus one per possible token, counted once: at most twice the file byte cap.
pub const MAX_PARSE_WORK: u64 = 8 << 20;
/// A separate depth bound for the non-linear parser and nested-fact paths.
pub const MAX_NESTING: usize = 512;
/// The most distinct input bytes in one in-process collection.
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
            "parse_work_limit: {} exceeds {MAX_PARSE_WORK} byte/token units or {MAX_NESTING} nesting levels",
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
    seen: HashMap<PathBuf, u64>,
    #[cfg(any(test, feature = "test-tree"))]
    reads: u64,
    hit: Option<WorkLimit>,
}

#[cfg(any(test, feature = "test-tree"))]
pub(crate) fn charged_bytes() -> Option<u64> {
    limits()
        .get(&thread::current().id())
        .map(|budget| MAX_SCAN_BYTES - budget.remaining)
}

#[cfg(any(test, feature = "test-tree"))]
pub(crate) fn read_bytes() -> Option<u64> {
    limits()
        .get(&thread::current().id())
        .map(|budget| budget.reads)
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
            seen: HashMap::new(),
            #[cfg(any(test, feature = "test-tree"))]
            reads: 0,
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

pub(crate) fn permits(root: &Path, path: &str, bytes: &[u8]) -> bool {
    let mut limits = limits();
    let Some(budget) = limits.get_mut(&thread::current().id()) else {
        return true;
    };
    if budget.hit.is_some() {
        return false;
    }
    #[cfg(any(test, feature = "test-tree"))]
    {
        budget.reads += bytes.len() as u64;
    }
    let key = root.join(crate::paths::normpath(path));
    let previous = budget.seen.get(&key).copied().unwrap_or(0);
    let extra = (bytes.len() as u64).saturating_sub(previous);
    let scope = if over(bytes) || crate::nesting::over(bytes, MAX_NESTING) {
        Some(WorkScope::File)
    } else if extra > budget.remaining {
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
    budget.remaining -= extra;
    budget.seen.insert(key, previous + extra);
    true
}

/// A parser's actual tree depth also covers grammar constructs without paired byte delimiters.
pub fn refuse_depth(path: &str) {
    let mut limits = limits();
    let Some(budget) = limits.get_mut(&thread::current().id()) else {
        return;
    };
    budget.hit.get_or_insert_with(|| WorkLimit {
        path: path.to_owned(),
        scope: WorkScope::File,
    });
}

/// The active in-process depth bound; standalone collectors keep their existing host bounds.
pub fn depth_limit() -> Option<usize> {
    limits()
        .contains_key(&thread::current().id())
        .then_some(MAX_NESTING)
}

/// Bytes and possible tokens each count once; a word run is one token.
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
        charge += 1;
        if charge + tokens > budget {
            return true;
        }
    }
    false
}

#[cfg(test)]
#[path = "work_tests.rs"]
mod tests;
