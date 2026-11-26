// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply: the typed records of one request and their encoding into the compressed stream.

use archkeel_facts::envelope::validation::{InterfaceNeed, Registered};
use archkeel_facts::envelope::{
    Evidence, Input, LimitSupport, Profile, ProfileLimits, Provenance, Reply, Role, SectionName,
    TypeReach, Validation,
};
use archkeel_facts::request::RustRequest;
use archkeel_facts::{CallFact, GapFact, ImportFact, Record, SymbolFact};
use archkeel_wire::protocol::Version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};
use archkeel_wire::typed::assemble;

use crate::builder::Builder;
use crate::tree::Walked;
use crate::type_reach::Reached;
use archkeel_snapshot::Snapshot;

const SECTIONS: [&str; 4] = ["imports", "symbols", "unknowns", "calls"];
const FEATURES: [&str; 1] = ["rust-crate-edges"];
/// The feature of the linked reply: each import names its item and its route (AD-604).
const ROUTES_FEATURE: &str = "rust-item-routes-v2";
/// The basis of the route proofs (AD-608, #1779): a compile error rules out a second binding of
/// a name, so the scan reads code that rustc accepts. Every typed reply states it.
const COMPILE_PREMISE: &str = "the Rust code compiles (rustc accepts it)";

/// The basis and the assumption that the identity proofs of registry crates rest on (AD-774). The
/// collector reads the Cargo settings of the repository; it cannot see the settings of the machine
/// that builds. A literal, not `concat!`: a macro call in the collector is a gap that the scan of
/// ArchKeel itself reports.
const LOCK_PREMISE: &str = "the Rust code compiles (rustc accepts it); registry crates are built from the identity that Cargo.lock records; no outside source replacement";

/// The validation table of the collector (AD-688; `evaluate.py:1055-1056`, `ir/profiles.py:227-252`):
/// the sections `imports` and `unknowns` and optionally `calls` and `symbols`, the crate edges and the routes
/// as optional features, no construct capability. An interface statement holds exactly when the
/// reply states the routes (AD-604). The standard library is `std`, `core` and `alloc`.
fn validation() -> Validation {
    use SectionName::{Calls, Imports, Symbols, Unknowns};
    let features = [FEATURES[0], ROUTES_FEATURE];
    Validation {
        registered: vec![Registered::of(&[Imports, Unknowns], &[])
            .with_optional_sections(&[Calls, Symbols])
            .with_optional_features(&features)],
        interface: InterfaceNeed::Feature(ROUTES_FEATURE.to_owned()),
        standard_library: Profile::Rust.as_str().to_owned(),
    }
}

/// The facts of one request, as the typed records of `archkeel-facts` (AD-345) and the small lists.
/// `encode` writes the gaps once: they are the section `unknowns` and the gaps of the coverage.
pub(crate) struct Collected {
    pub head: Head,
    pub calls: Vec<Record<CallFact>>,
    pub imports: Vec<Record<ImportFact>>,
    pub symbols: Vec<Record<SymbolFact>>,
    pub gaps: Vec<Record<GapFact>>,
    named_sites: Builder,
    pub selected_files: Vec<String>,
    pub files_read: usize,
    pub evidence: Vec<Evidence>,
    /// The scan states `LOCK_PREMISE` with its verdict.
    pub lock_premise: bool,
    /// The binding values of the type-reach facts that the scan verified and used (AD-1116).
    pub reached: Option<Reached>,
}

impl Collected {
    /// The compressed reply for `version`.
    pub(crate) fn encode(self, version: Version) -> Result<Vec<u8>, String> {
        let (head, records) = self.parts();
        let mut bytes = Vec::new();
        encode_stream(version, head, &mut bytes, |writer| records.produce(writer))?;
        Ok(bytes)
    }

    /// The typed reply uses the same record producer as the compressed stream. The linked reply
    /// states that each import names its item with its publication route, so the core can
    /// decide the symbol selectors and the interface rule (AD-500, AD-604). The compressed
    /// stream keeps its frozen statement set, as the Python survey does (AD-504).
    pub(crate) fn typed(mut self, version: Version) -> Result<Reply, String> {
        let premise = self.lock_premise;
        let reached = self.reached.take();
        let (head, records) = self.parts();
        let mut reply = assemble(version, head, |writer| records.produce(writer))?;
        reply.facts.profile_limits = Some(ProfileLimits {
            dependency_symbols: LimitSupport::Supported,
            interface_boundary: LimitSupport::Supported,
            publication_surface: LimitSupport::Unsupported,
        });
        let features = &mut reply.facts.capabilities.resolution_features;
        features.push(ROUTES_FEATURE.to_owned());
        reply.facts.type_reach = reached.map(|found| TypeReach {
            rustc: found.rustc,
            target_triple: found.target_triple,
            driver_sha256: found.driver_sha256,
            cargo_lock_sha256: found.cargo_lock_sha256,
            members: found.members,
            configs: found.configs,
        });
        reply.facts.scope_premise = Some(
            (if premise {
                LOCK_PREMISE
            } else {
                COMPILE_PREMISE
            })
            .to_owned(),
        );
        Ok(reply)
    }

    fn parts(self) -> (Head, Records) {
        let Self {
            head,
            calls,
            imports,
            symbols,
            gaps,
            named_sites,
            selected_files,
            files_read,
            evidence,
            lock_premise: _,
            reached: _,
        } = self;
        (
            head,
            Records {
                calls,
                imports,
                symbols,
                named_sites,
                tail: Tail {
                    measures: None,
                    selected_files,
                    files_read,
                    gaps,
                    evidence,
                },
            },
        )
    }
}

struct Records {
    calls: Vec<Record<CallFact>>,
    imports: Vec<Record<ImportFact>>,
    symbols: Vec<Record<SymbolFact>>,
    named_sites: Builder,
    tail: Tail,
}

impl Records {
    fn produce(self, writer: &mut impl SectionSink) -> std::io::Result<Tail> {
        let Self {
            calls,
            imports,
            symbols,
            named_sites,
            tail,
        } = self;
        writer.write_typed_section::<ImportFact>(|emit| imports.iter().for_each(emit))?;
        writer.write_typed_section::<SymbolFact>(|emit| symbols.iter().for_each(emit))?;
        writer.write_typed_section::<GapFact>(|emit| {
            tail.gaps.iter().for_each(&mut *emit);
            named_sites.stream_named_sites(emit);
        })?;
        writer.write_typed_section::<CallFact>(|emit| calls.iter().for_each(emit))?;
        Ok(tail)
    }
}

impl Builder {
    pub(crate) fn finish(
        mut self,
        request: &RustRequest,
        provenance: Provenance,
        scope: Vec<String>,
        selected: Vec<String>,
        walked: Walked,
        source: Snapshot,
    ) -> Collected {
        let files_read = walked.modules.len() + self.manifests.len();
        // Drop parsed module trees before materializing gap records (#1942).
        drop(walked);
        let (gaps, named_sites) = self.take_gaps_and_named_sites();
        let Self {
            evidence,
            mut files,
            calls,
            mut imports,
            mut symbols,
            targets,
            lock_premise,
            ..
        } = self;
        files.sort_by(|a, b| a.rel_path.cmp(&b.rel_path));
        imports.sort_by(|a, b| a.id.cmp(&b.id));
        symbols.sort_by(|a, b| a.id.cmp(&b.id));
        let head = Head {
            provenance,
            git_head: request.snapshot.git_head.clone(),
            dirty: serde_json::to_value(&request.snapshot.dirty).unwrap_or_default(),
            scope,
            sections: SECTIONS.to_vec(),
            features: FEATURES.to_vec(),
            constructs: Vec::new(),
            inputs: source.inputs(|path, digest, selected| Input {
                path: path.to_owned(),
                digest: digest.to_owned(),
                role: Role::of_read(selected),
            }),
            source_digest: None,
            files,
            imports: targets,
            validation: validation(),
        };
        Collected {
            head,
            calls,
            imports,
            symbols,
            gaps,
            named_sites,
            selected_files: selected,
            files_read,
            evidence: evidence.into_values().collect(),
            lock_premise,
            reached: None,
        }
    }
}
