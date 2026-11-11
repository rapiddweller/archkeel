// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The string table of `architecture.json`: count the texts, keep the profitable ones, write a
//! text as its reference (`ir/codec_strings.py`, observation policy; AD-346).
//!
//! A text of a shell row is counted by its index in the frame's text list, so it is never copied.
//! The other texts are counted twice: the first pass counts only a hash of each text, the second
//! keeps an exact count for a text whose hash came twice or more. Most of these texts are ids that
//! occur once, so they never enter a map; a hash collision only adds a text to the exact count.
//! The table borrows the shell texts, and a text finds its reference by a binary search of the
//! sorted table, so no text is held twice.

use std::borrow::Cow;
use std::collections::hash_map::DefaultHasher;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};

use serde_json::Value;

use crate::pyjson::{write_text, Texts};
use crate::shell::Shell;

/// Whether a text can enter the table at all; `profitable` needs 8 code points or `$$m`. Only
/// these texts are counted, so the counts hold no short id or word.
fn candidate(text: &str) -> bool {
    text == "$$m" || text.chars().nth(7).is_some()
}

/// `observation_profitable` of `ir/codec_strings.py`; a length counts code points.
pub(crate) fn profitable(text: &str, occurrences: u64) -> bool {
    let length = text.chars().count() as u64;
    text == "$$m"
        || (occurrences >= 2 && length >= 8 && (occurrences - 1) * length > occurrences * 8 + 100)
}

/// `observation_escaped`: the missing marker and the spellings of a reference.
pub(crate) fn escaped(text: &str) -> bool {
    let digits = |rest: &str| !rest.is_empty() && rest.bytes().all(|b| b.is_ascii_digit());
    text == "$m"
        || text == "$$m"
        || text.strip_prefix('$').is_some_and(digits)
        || text
            .strip_prefix("$$")
            .is_some_and(|rest| digits(rest.trim_start_matches('$')))
}

/// The occurrences of each candidate text of one observation.
pub(crate) struct Counts<'a> {
    shell_texts: &'a Shell,
    shell: Vec<u64>,
    /// The first pass: occurrences of each text hash, up to 2.
    seen: HashMap<u64, u8>,
    exact: bool,
    other: HashMap<String, u64>,
}

fn hashed(text: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    text.hash(&mut hasher);
    hasher.finish()
}

impl<'a> Counts<'a> {
    pub(crate) fn new(shell_texts: &'a Shell) -> Self {
        Counts {
            shell_texts,
            shell: vec![0; shell_texts.all_texts().count()],
            seen: HashMap::new(),
            exact: false,
            other: HashMap::new(),
        }
    }

    /// A text of a stored record or of a plain shell entry.
    pub(crate) fn text(&mut self, text: &str) {
        if !candidate(text) {
            return;
        }
        let seen = self.seen.entry(hashed(text)).or_insert(0);
        if !self.exact {
            *seen = seen.saturating_add(1).min(2);
            return;
        }
        if *seen < 2 {
            return;
        }
        match self.other.get_mut(text) {
            Some(count) => *count += 1,
            None => {
                self.other.insert(text.to_owned(), 1);
            }
        }
    }

    /// The texts of a plain value, without the keys of its objects.
    pub(crate) fn value(&mut self, value: &Value) {
        match value {
            Value::String(text) => self.text(text),
            Value::Array(items) => items.iter().for_each(|item| self.value(item)),
            Value::Object(map) => map.values().for_each(|item| self.value(item)),
            _ => {}
        }
    }

    /// Start the second pass. A shell text adds its occurrences to its hash, so a text that the
    /// shell and a stored record each hold once is counted exactly.
    pub(crate) fn exact(&mut self) {
        for (text, count) in self.shell_texts.all_texts().zip(&self.shell) {
            if *count > 0 && candidate(text) {
                let seen = self.seen.entry(hashed(text)).or_insert(0);
                *seen = seen
                    .saturating_add(u8::try_from(*count).unwrap_or(2))
                    .min(2);
            }
        }
        self.exact = true;
    }

    /// The texts of the cell of a shell row at `at`: they are counted by index.
    pub(crate) fn cell(&mut self, at: usize) {
        let counts = &mut self.shell;
        self.shell_texts.texts_of(at, &mut |index| {
            if let Some(count) = counts.get_mut(index) {
                *count += 1;
            }
        });
    }

    /// The sorted table of the profitable texts. A text of the shell and of a stored record
    /// counts once with the sum of both.
    pub(crate) fn table(self) -> Interned<'a> {
        let Counts {
            shell_texts,
            shell,
            mut other,
            ..
        } = self;
        let mut table: Vec<Cow<'a, str>> = Vec::new();
        let counted = shell_texts.all_texts().zip(shell);
        for (text, count) in counted.filter(|(text, count)| *count > 0 && candidate(text)) {
            let total = count + other.remove(text).unwrap_or(0);
            if profitable(text, total) {
                table.push(Cow::Borrowed(text));
            }
        }
        table.extend(
            other
                .into_iter()
                .filter(|(text, count)| profitable(text, *count))
                .map(|(text, _)| Cow::Owned(text)),
        );
        table.sort_unstable();
        Interned { table }
    }
}

/// Writes a text as its table reference, or escaped when it looks like a reference.
pub(crate) struct Interned<'a> {
    pub(crate) table: Vec<Cow<'a, str>>,
}

impl Texts for Interned<'_> {
    fn write(&self, text: &str, out: &mut Vec<u8>) -> Result<(), String> {
        if let Ok(index) = self.table.binary_search_by(|item| item.as_ref().cmp(text)) {
            out.extend_from_slice(format!("\"${index}\"").as_bytes());
            Ok(())
        } else if escaped(text) {
            write_text(&format!("${text}"), out)
        } else {
            write_text(text, out)
        }
    }
}
