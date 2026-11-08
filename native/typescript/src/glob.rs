// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! TSConfig wildcards with the semantics of `config._wildcard`, matched part by part.
//!
//! A path is root-anchored, for example `/src/a.ts`. A `*` never crosses `/`. A `**` matches
//! zero or more directories. For files and directories, a wildcard never matches a dot name or
//! `node_modules`, `bower_components` or `jspm_packages`, and a file `*` never consumes the dot
//! of a final `.min.js`.

use crate::paths::normpath;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Usage {
    Files,
    Directories,
    Exclude,
}

#[derive(Clone, Debug, PartialEq)]
enum Part {
    Deep,
    Name(Vec<Token>),
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Token {
    Literal(char),
    Star,
    Question,
}

const RESERVED: [&str; 3] = ["node_modules", "bower_components", "jspm_packages"];

/// One compiled include or exclude spec.
#[derive(Clone, Debug, PartialEq)]
pub struct Pattern {
    usage: Usage,
    parts: Vec<Part>,
}

impl Pattern {
    /// Compile a snapshot-relative spec; `None` when an include ends in `**`.
    pub fn new(spec: &str, usage: Usage) -> Option<Self> {
        let path = normpath(&format!("/{spec}"));
        let mut names: Vec<&str> = path.split('/').skip(1).filter(|n| !n.is_empty()).collect();
        let last = names.last().copied().unwrap_or("");
        if usage != Usage::Exclude {
            if last == "**" {
                return None;
            }
            if !last.contains(['.', '*', '?']) {
                names.extend(["**", "*"]);
            }
        }
        let parts = names
            .into_iter()
            .map(|name| match name {
                "**" => Part::Deep,
                _ => Part::Name(name.chars().map(Token::from).collect()),
            })
            .collect();
        Some(Self { usage, parts })
    }

    /// Whether the pattern selects the root-anchored `path`.
    pub fn matches(&self, path: &str) -> bool {
        let names: Vec<&str> = path.split('/').filter(|n| !n.is_empty()).collect();
        match self.usage {
            Usage::Files => self.full(&self.parts, &names),
            Usage::Directories => self.prefix_of_pattern(&self.parts, &names),
            Usage::Exclude => (0..=names.len()).any(|k| self.full(&self.parts, &names[..k])),
        }
    }

    fn full(&self, parts: &[Part], names: &[&str]) -> bool {
        match parts.split_first() {
            None => names.is_empty(),
            Some((Part::Deep, rest)) => {
                self.full(rest, names)
                    || names
                        .first()
                        .is_some_and(|name| self.deep_name(name) && self.full(parts, &names[1..]))
            }
            Some((Part::Name(tokens), rest)) => names.first().is_some_and(|name| {
                self.name(tokens, name, names.len() == 1) && self.full(rest, &names[1..])
            }),
        }
    }

    // A directory is reachable when its names match the start of the pattern.
    fn prefix_of_pattern(&self, parts: &[Part], names: &[&str]) -> bool {
        if names.is_empty() {
            return true;
        }
        match parts.split_first() {
            None => false,
            Some((Part::Deep, rest)) => {
                self.prefix_of_pattern(rest, names)
                    || (self.deep_name(names[0]) && self.prefix_of_pattern(parts, &names[1..]))
            }
            Some((Part::Name(tokens), rest)) => {
                self.name(tokens, names[0], false) && self.prefix_of_pattern(rest, &names[1..])
            }
        }
    }

    fn deep_name(&self, name: &str) -> bool {
        self.usage == Usage::Exclude
            || (!name.starts_with('.') && !name.is_empty() && !RESERVED.contains(&name))
    }

    fn name(&self, tokens: &[Token], name: &str, last: bool) -> bool {
        let wildcard = tokens.iter().any(|token| !token.literal());
        if self.usage != Usage::Exclude && wildcard && RESERVED.contains(&name) {
            return false;
        }
        let characters: Vec<char> = name.chars().collect();
        let leading = self.usage != Usage::Exclude;
        match tokens.first() {
            Some(Token::Star) if leading => {
                // `(?:[^./]<star>)?`: empty, or a first character that is not a dot.
                self.tokens(&tokens[1..], &characters, last)
                    || characters.first().is_some_and(|first| {
                        *first != '.' && self.tokens(tokens, &characters[1..], last)
                    })
            }
            Some(Token::Question) if leading => characters.first().is_some_and(|first| {
                *first != '.' && self.tokens(&tokens[1..], &characters[1..], last)
            }),
            _ => self.tokens(tokens, &characters, last),
        }
    }

    fn tokens(&self, tokens: &[Token], characters: &[char], last: bool) -> bool {
        match tokens.split_first() {
            None => characters.is_empty(),
            Some((Token::Literal(expected), rest)) => {
                characters.first() == Some(expected) && self.tokens(rest, &characters[1..], last)
            }
            Some((Token::Question, rest)) => {
                !characters.is_empty() && self.tokens(rest, &characters[1..], last)
            }
            Some((Token::Star, rest)) => (0..=characters.len()).any(|taken| {
                self.star_takes(&characters[..taken], &characters[taken..], last)
                    && self.tokens(rest, &characters[taken..], last)
            }),
        }
    }

    // A file `*` must not take the dot that starts a final `.min.js`.
    fn star_takes(&self, taken: &[char], after: &[char], last: bool) -> bool {
        if self.usage != Usage::Files || !last {
            return true;
        }
        let mut remainder: Vec<char> = taken.to_vec();
        remainder.extend_from_slice(after);
        taken.iter().enumerate().all(|(index, character)| {
            *character != '.' || remainder[index + 1..].iter().collect::<String>() != "min.js"
        })
    }
}

impl Token {
    fn literal(self) -> bool {
        matches!(self, Token::Literal(_))
    }
}

impl From<char> for Token {
    fn from(character: char) -> Self {
        match character {
            '*' => Token::Star,
            '?' => Token::Question,
            other => Token::Literal(other),
        }
    }
}

#[cfg(test)]
#[path = "glob_tests.rs"]
mod tests;
