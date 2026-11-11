// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply: the typed records of one request and their encoding into the compressed stream.

use archkeel_facts::envelope::{Evidence, Provenance};
use archkeel_facts::request::RustRequest;
use archkeel_facts::{GapFact, ImportFact, Record, SymbolFact};
use archkeel_wire::protocol::Version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};

use crate::builder::Builder;
use crate::tree::Walked;
use archkeel_snapshot::Snapshot;

const SECTIONS: [&str; 3] = ["imports", "symbols", "unknowns"];
const FEATURES: [&str; 1] = ["rust-crate-edges"];

/// The facts of one request, as the typed records of `archkeel-facts` (AD-345) and the small lists.
/// `encode` writes the gaps once: they are the section `unknowns` and the gaps of the coverage.
pub struct Collected {
    pub head: Head,
    pub imports: Vec<Record<ImportFact>>,
    pub symbols: Vec<Record<SymbolFact>>,
    pub gaps: Vec<Record<GapFact>>,
    pub selected_files: Vec<String>,
    pub files_read: usize,
    pub evidence: Vec<Evidence>,
}

impl Collected {
    /// The compressed reply for `version`.
    pub fn encode(self, version: Version) -> Result<Vec<u8>, String> {
        let Self {
            head,
            imports,
            symbols,
            gaps,
            selected_files,
            files_read,
            evidence,
        } = self;
        let mut bytes = Vec::new();
        encode_stream(version, head, &mut bytes, |writer| {
            writer.write_typed_section::<ImportFact>(|emit| imports.iter().for_each(emit))?;
            writer.write_typed_section::<SymbolFact>(|emit| symbols.iter().for_each(emit))?;
            writer.write_typed_section::<GapFact>(|emit| gaps.iter().for_each(emit))?;
            Ok(Tail {
                selected_files,
                files_read,
                gaps,
                evidence,
            })
        })?;
        Ok(bytes)
    }
}

impl Builder {
    pub(crate) fn finish(
        self,
        request: &RustRequest,
        provenance: Provenance,
        scope: Vec<String>,
        selected: Vec<String>,
        walked: &Walked,
        source: Snapshot,
    ) -> Collected {
        let mut files = self.files;
        files.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
        let mut imports = self.imports;
        imports.sort_by(|a, b| a.id.cmp(&b.id));
        let mut symbols = self.symbols;
        symbols.sort_by(|a, b| a.id.cmp(&b.id));
        let head = Head {
            provenance,
            git_head: request.snapshot.git_head.clone(),
            dirty: serde_json::to_value(&request.snapshot.dirty).unwrap_or_default(),
            scope,
            sections: SECTIONS.to_vec(),
            features: FEATURES.to_vec(),
            constructs: Vec::new(),
            inputs: source.inputs(),
            source_digest: None,
            files,
            imports: self.targets,
        };
        Collected {
            head,
            imports,
            symbols,
            gaps: self.gaps.into_values().collect(),
            selected_files: selected,
            files_read: walked.modules.len() + self.manifests.len(),
            evidence: self.evidence.into_values().collect(),
        }
    }
}
