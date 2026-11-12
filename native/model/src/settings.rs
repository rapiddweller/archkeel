// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the shell tells the core about a run (AD-372): the namespace of the configuration, the
//! profile of the reply and the top-level names of the standard library of that profile.
//!
//! The shell is the only reader of the configuration and owns the table of profiles. The core
//! parses no configuration file and names no language, so it takes these as typed values. It
//! binds them to the reply by a check (`check`, `Model::derive`): the profile must be the profile
//! of the reply, and each module of the reply must lie in the namespace.
//!
//! Slice S4 adds the producer of the reply (AD-344, AD-378): only the host starts the collector,
//! so only the shell knows it. The default is the sound one: a reply of an external collector,
//! which gives no PASS. The producer of the shell is a claim, not evidence (AD-388): the graph
//! trusts a reply only when the shell claims a trusted producer and the reply names the collector
//! of its own profile as its adapter (`bound`). So a caller cannot make the reply of another
//! adapter trusted. The standard library of the shell must lie in the pinned list of the profile
//! of the reply (`archkeel_store::standard_library`): a caller cannot widen it by word.
//!
//! Slice S5 adds the source of the root contract (AD-380): the reference engine cites the
//! contract file in each `layer_order` row (`check/observation.py` `_layer_order_evidence`). The
//! shell reads that file, so it sends its path and bytes; the model binds them to the parsed
//! contract by the digest of the bytes.
//!
//! Slice S7 adds the scan roots of the configuration (AD-384): the cycle receipts and the
//! receipt of `complete_requires` ask whether the roots hold each module file. The shell reads
//! the roots; the core binds them to the reply: the collector writes each root that it scanned in
//! `source.scope` (`root/**` for a directory, else the root), so the roots of the request must
//! be exactly these labels in their order. A caller cannot widen a root by word.

use crate::ownership::in_scope;
use crate::reason::Refusal;

/// The largest number of standard library names that a request can carry.
pub const STANDARD_LIBRARY_LIMIT: usize = 1024;
/// The longest standard library name in bytes.
pub const STANDARD_NAME_LIMIT: usize = 128;

/// The settings of one run.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Settings {
    namespace: String,
    profile: String,
    standard_library: Vec<String>,
    producer: Producer,
    contract_source: Option<ContractSource>,
    roots: Option<Vec<String>>,
}

/// The evidence of the contract file and the digest of the bytes that it cites.
#[derive(Clone, Debug, PartialEq, Eq)]
struct ContractSource {
    evidence: String,
    digest: String,
}

/// Who produced the reply, as the host decides it (`cli/observe.py` `observer_for`).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Producer {
    /// A collector that the host does not trust for a PASS: an external command without a
    /// pinned digest, or a producer that the shell does not name.
    #[default]
    External,
    /// The bundled collector, or an external command with a pinned digest.
    Trusted,
}

impl Settings {
    /// The settings of a namespace, the profile that the shell read and its standard library.
    pub fn new(namespace: String, profile: String, standard_library: Vec<String>) -> Self {
        Settings {
            namespace,
            profile,
            standard_library,
            producer: Producer::External,
            contract_source: None,
            roots: None,
        }
    }

    /// The same settings with the scan roots of the configuration, in their order.
    pub fn with_roots(self, roots: Vec<String>) -> Self {
        Settings {
            roots: Some(roots),
            ..self
        }
    }

    /// The scan roots, when the shell sent them and they agree with the reply (`Graph::derive`
    /// refuses the settings otherwise).
    pub(crate) fn roots(&self) -> Option<&[String]> {
        self.roots.as_deref()
    }

    /// The settings refused by name, unless the scan roots are the scope labels of the reply,
    /// one label for each root and in the same order. Settings without roots bind nothing: a
    /// receipt that needs the roots then names `Part::ScanRoots`.
    pub(crate) fn bind_roots(&self, scope: &[String]) -> Result<(), Refusal> {
        let Some(roots) = &self.roots else {
            return Ok(());
        };
        let fits = |(root, label): (&String, &String)| {
            // A root with `*` could read as a label of another root, so it is refused.
            !root.is_empty()
                && !root.contains(['\0', '*'])
                && (label == root || label.strip_suffix("/**") == Some(root.as_str()))
        };
        // One root for each label: the reply bounds the number of roots.
        if roots.len() != scope.len() || !roots.iter().zip(scope).all(fits) {
            return Err(Refusal::ScanRoots);
        }
        Ok(())
    }

    /// The same settings with the path and the bytes of the root contract file. The evidence is
    /// `file_evidence` of `ir/source_records.py:120`: line 1 when the first line holds text after
    /// trailing spaces, else line 0.
    pub fn with_contract_source(self, path: &str, bytes: &[u8]) -> Self {
        let text = String::from_utf8_lossy(bytes);
        let first = text.split(line_break).next().unwrap_or_default();
        let blank = first.trim_end_matches(reference_space).is_empty();
        let (line, end) = if blank { (0, 0) } else { (1, 1) };
        let evidence = archkeel_facts::identity::evidence_id(path, line, end, 0);
        let digest = archkeel_facts::identity::sha256_hex(bytes);
        let contract_source = Some(ContractSource { evidence, digest });
        Settings {
            contract_source,
            ..self
        }
    }

    /// The evidence id of the contract file when its bytes have `digest`, the digest of the
    /// parsed contract. Other bytes or no source give `None`: the reference engine then cites
    /// no file and gives the rule no receipt.
    pub fn contract_evidence(&self, digest: &str) -> Option<&str> {
        self.contract_source
            .as_ref()
            .filter(|source| source.digest == digest)
            .map(|source| source.evidence.as_str())
    }

    /// The same settings with the producer that the shell claims. The graph trusts it only with
    /// the evidence of the reply (`bound`).
    pub fn with_producer(self, producer: Producer) -> Self {
        Settings { producer, ..self }
    }

    /// The producer: the claim of the shell, and in the settings of a graph the producer bound to
    /// the reply (`Graph::derive`).
    pub fn producer(&self) -> Producer {
        self.producer
    }

    /// The settings bound to a reply: a trusted claim holds only when the adapter of the reply is
    /// the collector of its profile. Any other adapter is an external producer.
    pub(crate) fn bound(self, adapter: &str, profile: &str) -> Self {
        let producer = match self.producer {
            Producer::Trusted if adapter == profile => Producer::Trusted,
            Producer::Trusted | Producer::External => Producer::External,
        };
        Settings { producer, ..self }
    }

    /// The dotted namespace of the configuration.
    pub fn namespace(&self) -> &str {
        &self.namespace
    }

    /// True when `root` is a top-level name of the standard library of the profile.
    pub fn standard(&self, root: &str) -> bool {
        self.standard_library.iter().any(|name| name == root)
    }

    /// The settings refused by name, unless they hold for a reply of `profile`, whose pinned
    /// standard library is `pinned`.
    pub(crate) fn check(&self, profile: &str, pinned: &[&str]) -> Result<(), Refusal> {
        if self.profile != profile {
            return Err(Refusal::ProfileMismatch);
        }
        let names = &self.standard_library;
        if names.iter().any(|name| !pinned.contains(&name.as_str())) {
            return Err(Refusal::StandardLibrary(
                "a name outside the pinned standard library of the profile",
            ));
        }
        if names.len() > STANDARD_LIBRARY_LIMIT {
            return Err(Refusal::StandardLibrary("more names than the limit"));
        }
        if names
            .iter()
            .any(|name| name.is_empty() || name.len() > STANDARD_NAME_LIMIT || name.contains('\0'))
        {
            return Err(Refusal::StandardLibrary("an empty, long or NUL name"));
        }
        let mut sorted: Vec<&str> = names.iter().map(String::as_str).collect();
        sorted.sort_unstable();
        if sorted.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(Refusal::StandardLibrary("a duplicate name"));
        }
        Ok(())
    }

    /// The module refused by name, unless it and its package lie in the namespace
    /// (`evaluate_source` raises a protocol error for the same files).
    pub(crate) fn admits(&self, module: &str, package: &str) -> Result<(), Refusal> {
        let namespace = self.namespace.as_str();
        let inside = in_scope(module, namespace)
            && in_scope(module, package)
            && (in_scope(package, namespace) || in_scope(namespace, package));
        if inside {
            Ok(())
        } else {
            Err(Refusal::OutsideNamespace(module.to_owned()))
        }
    }
}

#[cfg(test)]
#[path = "settings_tests.rs"]
mod tests;

/// A line break of `str.splitlines` in the reference engine.
fn line_break(c: char) -> bool {
    matches!(
        c,
        '\n' | '\r'
            | '\u{0b}'
            | '\u{0c}'
            | '\u{1c}'
            | '\u{1d}'
            | '\u{1e}'
            | '\u{85}'
            | '\u{2028}'
            | '\u{2029}'
    )
}

/// A space of `str.rstrip` without an argument in the reference engine (`str.isspace`).
fn reference_space(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}')
}
