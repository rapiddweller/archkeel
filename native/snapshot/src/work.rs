// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A conservative parse-work charge before any in-process collector sees bytes (AD-420).

use std::cell::RefCell;

/// The most charged work in one file. Each byte costs one plus all possible tokens before it.
pub const MAX_PARSE_WORK: u64 = 1 << 30;
/// The most bytes returned by all snapshot reads in one in-process collection.
pub const MAX_SCAN_BYTES: u64 = 16 << 20;

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

// The thread boundary covers every linked collector without changing its wire request.
thread_local! {
    static LIMIT: RefCell<Option<Budget>> = const { RefCell::new(None) };
}

struct Budget {
    remaining: u64,
    hit: Option<WorkLimit>,
}

/// Bound every snapshot read on this thread. A hit discards the whole result, including facts
/// that the collector made before the hit. The binary collector keeps its existing host limit.
pub fn bounded<T>(work: impl FnOnce() -> T) -> Result<T, WorkLimit> {
    struct Restore(bool);
    impl Drop for Restore {
        fn drop(&mut self) {
            if self.0 {
                LIMIT.with(|limit| *limit.borrow_mut() = None);
            }
        }
    }
    let restore = Restore(LIMIT.with(|limit| {
        let mut limit = limit.borrow_mut();
        if limit.is_some() {
            return false;
        }
        *limit = Some(Budget {
            remaining: MAX_SCAN_BYTES,
            hit: None,
        });
        true
    }));
    let result = work();
    let hit = LIMIT.with(|limit| {
        limit
            .borrow()
            .as_ref()
            .and_then(|budget| budget.hit.clone())
    });
    drop(restore);
    match hit {
        Some(hit) => Err(hit),
        None => Ok(result),
    }
}

pub(crate) fn permits(path: &str, bytes: &[u8]) -> bool {
    LIMIT.with(|limit| {
        let mut limit = limit.borrow_mut();
        let Some(budget) = limit.as_mut() else {
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
    })
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
