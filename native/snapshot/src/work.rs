// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A conservative parse-work charge before any in-process collector sees bytes (AD-420).

use std::cell::RefCell;

/// The most charged work in one file. Each byte costs one plus all possible tokens before it.
pub const MAX_PARSE_WORK: u64 = 1 << 30;

/// A file that the in-process collector must not parse.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkLimit {
    pub path: String,
}

impl std::fmt::Display for WorkLimit {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            out,
            "parse_work_limit: {} exceeds {MAX_PARSE_WORK} charged units",
            self.path
        )
    }
}

thread_local! {
    static LIMIT: RefCell<Option<Option<WorkLimit>>> = const { RefCell::new(None) };
}

/// Bound every snapshot read on this thread. A hit discards the whole result, including facts
/// that the collector made before the hit. The binary collector keeps its existing host limit.
pub fn bounded<T>(work: impl FnOnce() -> T) -> Result<T, WorkLimit> {
    struct Restore(Option<Option<WorkLimit>>);
    impl Drop for Restore {
        fn drop(&mut self) {
            LIMIT.with(|limit| *limit.borrow_mut() = self.0.take());
        }
    }
    let restore = Restore(LIMIT.with(|limit| limit.replace(Some(None))));
    let result = work();
    let hit = LIMIT.with(|limit| limit.borrow().as_ref().and_then(Clone::clone));
    drop(restore);
    match hit {
        Some(hit) => Err(hit),
        None => Ok(result),
    }
}

pub(crate) fn permits(path: &str, bytes: &[u8]) -> bool {
    LIMIT.with(|limit| {
        let mut limit = limit.borrow_mut();
        let Some(hit) = limit.as_mut() else {
            return true;
        };
        if hit.is_some() {
            return false;
        }
        if over(bytes) {
            *hit = Some(WorkLimit {
                path: path.to_owned(),
            });
            return false;
        }
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
        if !byte.is_ascii_whitespace() && !(word && next_word) {
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
