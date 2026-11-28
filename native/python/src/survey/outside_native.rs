// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The modules of the scan that an extension file names (#1522, AD-770).
//!
//! An extension can import a module by its name (`PyImport_ImportModule("app.lib")`) and write it.
//! The text is not parsed: each dotted word names the module that is its longest prefix. Two
//! adjacent C string literals are one word (`"ap" "p.lib"`). Native code can walk the attributes
//! of the module that it names, so the module, each module below it and each package above it
//! escape. A compiled module, and a Python file that the collector cannot read, are read as bytes
//! in the same way. A Rust file is an extension only when it names the C API of Python.

use std::collections::HashSet;

use archkeel_snapshot::Snapshot;

use crate::module::first_part;

/// The suffixes of the files that can hold the code of an extension module.
const SUFFIXES: [&str; 20] = [
    ".c", ".h", ".cc", ".cpp", ".cxx", ".c++", ".hh", ".hpp", ".hxx", ".h++", ".m", ".mm", ".pyx",
    ".pxd", ".pxi", ".so", ".pyd", ".dylib", ".pyc", ".rs",
];

/// The words that make a Rust file an extension.
const RUST_API: [&[u8]; 4] = [b"pyo3", b"PyObject", b"PyImport", b"PyModule"];

/// The longest dotted word that the search keeps across two parts of a file.
const LONGEST: usize = 4096;

/// True for the path of an extension file.
pub(super) fn extension(rel: &str) -> bool {
    SUFFIXES.iter().any(|suffix| rel.ends_with(suffix))
}

/// The modules of `names` that the extension files `files` name.
pub(super) fn named(
    snapshot: &mut Snapshot,
    files: &[String],
    names: &HashSet<String>,
) -> HashSet<String> {
    let tops: HashSet<&str> = names.iter().map(|name| first_part(name)).collect();
    let mut found = HashSet::new();
    for rel in files {
        let mut words = Words {
            tops: &tops,
            found: HashSet::new(),
            word: Vec::new(),
            joining: None,
            // A word in a comment of a Rust file names nothing; the other languages keep them.
            rust: rel.ends_with(".rs").then(RustLexer::default),
        };
        let mut api = !rel.ends_with(".rs");
        let mut tail: Vec<u8> = Vec::new();
        snapshot.read_parts(rel, &mut |part| {
            if !api {
                tail.extend_from_slice(part);
                api = RUST_API.iter().any(|word| contains(&tail, word));
                let keep = Vec::len(&tail).saturating_sub(16);
                tail.drain(..keep);
            }
            words.feed(part);
        });
        words.flush();
        if api {
            for word in &words.found {
                found.extend(reached(word, names));
            }
        }
    }
    found
}

/// The modules that `text` reaches when it names a module of `names`: the module that is its
/// longest prefix, each module below it and each package above it.
pub(super) fn reached(text: &str, names: &HashSet<String>) -> Vec<String> {
    let parts: Vec<&str> = text.split('.').collect();
    let Some(module) = (1..=Vec::len(&parts))
        .rev()
        .map(|count| parts[..count].join("."))
        .find(|prefix| names.contains(String::as_str(prefix)))
    else {
        return Vec::new();
    };
    let below = format!("{module}.");
    names
        .iter()
        .filter(|name| {
            name.starts_with(&below) || module.starts_with(&format!("{name}.")) || **name == module
        })
        .cloned()
        .collect()
}

fn contains(part: &[u8], word: &[u8]) -> bool {
    // The byte count of the word; `len` on a slice reads as a pair gap of the self-check (#1571).
    part.windows(std::mem::size_of_val(word))
        .any(|window| window == word)
}

/// The dotted words of a text that comes in parts whose first part is one of `tops`.
struct Words<'t> {
    tops: &'t HashSet<&'t str>,
    found: HashSet<String>,
    word: Vec<u8>,
    /// After a `"` that ends a word: the blanks seen since, until the next `"` joins two literals.
    joining: Option<usize>,
    /// The comment state of a Rust file.
    rust: Option<RustLexer>,
}

impl Words<'_> {
    fn feed(&mut self, part: &[u8]) {
        for &byte in part {
            self.byte(byte);
        }
        if Vec::len(&self.word) > LONGEST {
            self.flush();
        }
    }

    fn byte(&mut self, byte: u8) {
        if self.rust.as_mut().is_some_and(|lexer| lexer.comment(byte)) {
            self.flush();
            return;
        }
        if let Some(blanks) = self.joining {
            match byte {
                b'"' => {
                    self.joining = None;
                    return;
                }
                b' ' | b'\t' | b'\r' | b'\n' if blanks < LONGEST => {
                    self.joining = Some(blanks + 1);
                    return;
                }
                _ => self.flush(),
            }
        }
        if byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'.' {
            self.word.push(byte);
        } else if byte == b'"' && !Vec::is_empty(&self.word) {
            self.joining = Some(0);
        } else {
            self.flush();
        }
    }

    fn flush(&mut self) {
        self.joining = None;
        let text = String::from_utf8_lossy(&self.word);
        let text = text.trim_matches('.');
        let valid = |part: &str| {
            part.chars()
                .next()
                .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
        };
        let top = self.tops.contains(first_part(text));
        if top && text.split('.').all(valid) {
            self.found.insert(text.to_owned());
        }
        self.word.clear();
    }
}

/// Where the bytes of a Rust file are: in code, a comment, a string or a character. Only a byte in
/// a comment is skipped. A doubt keeps the byte as code, so a name is never hidden by a wrong guess:
/// a string that is mistaken for code can only show more words, never fewer.
#[derive(Default)]
struct RustLexer {
    state: Lex,
    before: [u8; 2],
}

#[derive(Clone, Copy, Default)]
enum Lex {
    #[default]
    Code,
    Slash,
    Line,
    Block(u32),
    BlockStar(u32),
    BlockSlash(u32),
    Str,
    StrEscape,
    RawHash(usize),
    Raw {
        hashes: usize,
        closing: Option<usize>,
    },
    Quote,
    CharOne,
    CharEscape,
    CharEnd,
}

fn ident(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

impl RustLexer {
    /// The state after `byte` in a raw string (`r#"..."#`), or `None` when the `r` was no prefix.
    fn raw(&self, byte: u8) -> Option<Lex> {
        match (self.state, byte) {
            (Lex::RawHash(hashes), b'#') => Some(Lex::RawHash(hashes + 1)),
            (Lex::RawHash(hashes), b'"') => Some(Lex::Raw {
                hashes,
                closing: None,
            }),
            (Lex::Raw { hashes: 0, .. }, b'"') => Some(Lex::Code),
            (Lex::Raw { hashes, .. }, b'"') => Some(Lex::Raw {
                hashes,
                closing: Some(0),
            }),
            (
                Lex::Raw {
                    hashes,
                    closing: Some(seen),
                },
                b'#',
            ) if seen + 1 == hashes => Some(Lex::Code),
            (
                Lex::Raw {
                    hashes,
                    closing: Some(seen),
                },
                b'#',
            ) => Some(Lex::Raw {
                hashes,
                closing: Some(seen + 1),
            }),
            (Lex::Raw { hashes, .. }, _) => Some(Lex::Raw {
                hashes,
                closing: None,
            }),
            _ => None,
        }
    }

    /// True when `byte` is part of a comment.
    fn comment(&mut self, byte: u8) -> bool {
        let comment = self.step(byte);
        self.before = [self.before[1], byte];
        comment
    }

    fn step(&mut self, byte: u8) -> bool {
        loop {
            let [older, last] = self.before;
            let (next, comment) = match (self.state, byte) {
                (Lex::Code, b'/') => (Lex::Slash, false),
                (Lex::Code, b'"') => (Lex::Str, false),
                (Lex::Code, b'\'') => (Lex::Quote, false),
                (Lex::Code, b'r')
                    if !ident(last) || (matches!(last, b'b' | b'c') && !ident(older)) =>
                {
                    (Lex::RawHash(0), false)
                }
                (Lex::Code, _) => (Lex::Code, false),
                (Lex::Slash, b'/') => (Lex::Line, true),
                (Lex::Slash, b'*') => (Lex::Block(1), true),
                (Lex::Slash, _) => {
                    self.state = Lex::Code;
                    continue;
                }
                (Lex::Line, b'\n') => (Lex::Code, false),
                (Lex::Line, _) => (Lex::Line, true),
                (Lex::Block(depth), b'*') => (Lex::BlockStar(depth), true),
                (Lex::Block(depth), b'/') => (Lex::BlockSlash(depth), true),
                (Lex::Block(depth), _) => (Lex::Block(depth), true),
                (Lex::BlockStar(1), b'/') => (Lex::Code, true),
                (Lex::BlockStar(depth), b'/') => (Lex::Block(depth - 1), true),
                (Lex::BlockStar(depth), b'*') => (Lex::BlockStar(depth), true),
                (Lex::BlockStar(depth), _) => (Lex::Block(depth), true),
                (Lex::BlockSlash(depth), b'*') => (Lex::Block(depth + 1), true),
                (Lex::BlockSlash(depth), b'/') => (Lex::BlockSlash(depth), true),
                (Lex::BlockSlash(depth), _) => (Lex::Block(depth), true),
                (Lex::Str, b'\\') => (Lex::StrEscape, false),
                (Lex::Str, b'"') => (Lex::Code, false),
                (Lex::Str, _) => (Lex::Str, false),
                (Lex::StrEscape, _) => (Lex::Str, false),
                (Lex::RawHash(_) | Lex::Raw { .. }, _) => match self.raw(byte) {
                    Some(next) => (next, false),
                    None => {
                        self.state = Lex::Code;
                        continue;
                    }
                },
                (Lex::Quote, b'\\') => (Lex::CharEscape, false),
                (Lex::Quote, b'\'') => (Lex::Code, false),
                (Lex::Quote, _) => (Lex::CharOne, false),
                (Lex::CharOne, b'\'') => (Lex::Code, false),
                (Lex::CharOne, _) => {
                    // A lifetime, not a character: the byte is code.
                    self.state = Lex::Code;
                    continue;
                }
                (Lex::CharEscape, _) => (Lex::CharEnd, false),
                (Lex::CharEnd, b'\'') => (Lex::Code, false),
                (Lex::CharEnd, _) => (Lex::CharEnd, false),
            };
            self.state = next;
            return comment;
        }
    }
}

#[cfg(test)]
#[path = "outside_native_tests.rs"]
mod tests;
