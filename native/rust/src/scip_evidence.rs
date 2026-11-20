// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Prototype reader for explicitly supplied, source-bound SCIP files.

mod syntax;
mod wire;

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{BufReader, Read};
use std::path::Path;

use archkeel_facts::identity::{inside, sha256_hex};
use archkeel_snapshot::Snapshot;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use syntax::CallSite;
use wire::Field;

type Result<T> = std::result::Result<T, String>;
const INDEX_LIMIT: u64 = 64 << 20;
const MANIFEST_LIMIT: u64 = 8 << 20;
const REQUEST_LIMIT: u64 = 16 << 20;
const SOURCE_LIMIT: usize = 4096;
const OCCURRENCE_LIMIT: usize = 512_000;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    version: u32,
    index_sha256: String,
    files: BTreeMap<String, String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    calls: Vec<CallSite>,
    definitions: Vec<Definition>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Definition {
    id: String,
    evidence_id: String,
    kind: String,
}

#[derive(Clone, Eq, PartialEq, Serialize)]
struct Anchor {
    target_definition_id: String,
    evidence_id: String,
    path: String,
    line: u32,
}

#[derive(Serialize)]
struct Binding<'a> {
    call_id: &'a str,
    #[serde(flatten)]
    anchor: &'a Anchor,
}

#[derive(Serialize)]
struct Reply<'a> {
    index_sha256: String,
    manifest_sha256: String,
    manifest_files: &'a BTreeMap<String, String>,
    bindings: Vec<Binding<'a>>,
}

#[derive(Default)]
struct Join<'a> {
    documents: BTreeSet<String>,
    targets: BTreeMap<String, Option<Anchor>>,
    references: BTreeMap<&'a str, Option<String>>,
    occurrences: usize,
}

pub(super) fn run(stack_bytes: usize) -> Result<Vec<u8>> {
    let args = std::env::args().skip(2).collect::<Vec<_>>();
    let [root, index, manifest] = args.as_slice() else {
        return Err("usage: scip-evidence ROOT INDEX MANIFEST".to_owned());
    };
    let request = bounded_read(&mut std::io::stdin().lock(), REQUEST_LIMIT)?;
    let request: Request = serde_json::from_slice(&request).map_err(|e| e.to_string())?;
    let (root, index, manifest) = (root.clone(), index.clone(), manifest.clone());
    std::thread::Builder::new()
        .stack_size(stack_bytes)
        .spawn(move || {
            archkeel_snapshot::work::bounded(|| {
                join(&root, Path::new(&index), Path::new(&manifest), request)
            })
            .map_err(|error| error.to_string())?
        })
        .map_err(|error| error.to_string())?
        .join()
        .map_err(|_| "SCIP worker stopped".to_owned())?
}

fn bounded_read(input: &mut dyn Read, max: u64) -> Result<Vec<u8>> {
    let mut result = Vec::new();
    input
        .take(max + 1)
        .read_to_end(&mut result)
        .map_err(|e| e.to_string())?;
    if result.len() as u64 > max {
        return Err("SCIP input exceeds its byte limit".to_owned());
    }
    Ok(result)
}

fn regular(path: &Path, max: u64) -> Result<File> {
    let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    if !meta.is_file() || meta.len() > max {
        return Err("SCIP input must be a bounded regular file".to_owned());
    }
    File::open(path).map_err(|e| e.to_string())
}

fn source_bytes(snapshot: &mut Snapshot, path: &str, expected: &str) -> Result<Vec<u8>> {
    if !inside(path) || snapshot.real(path).as_deref() != Some(path) {
        return Err(format!("invalid SCIP source path: {path}"));
    }
    let bytes = snapshot
        .read(path)
        .ok_or_else(|| format!("unreadable SCIP source: {path}"))?;
    if sha256_hex(&bytes) != expected {
        return Err(format!("stale SCIP source: {path}"));
    }
    Ok(bytes)
}

fn join(root: &str, index: &Path, manifest: &Path, request: Request) -> Result<Vec<u8>> {
    let raw = bounded_read(&mut regular(manifest, MANIFEST_LIMIT)?, MANIFEST_LIMIT)?;
    let manifest_sha256 = sha256_hex(&raw);
    let manifest: Manifest = serde_json::from_slice(&raw).map_err(|error| error.to_string())?;
    if manifest.version != 1 || manifest.files.len() > SOURCE_LIMIT || manifest.files.is_empty() {
        return Err("unsupported SCIP manifest version or file count".to_owned());
    }
    if request.calls.len() > 100_000 || request.definitions.len() > 100_000 {
        return Err("SCIP request exceeds its row limit".to_owned());
    }
    let mut snapshot = Snapshot::open_root(root)?;
    for (path, digest) in &manifest.files {
        source_bytes(&mut snapshot, path, digest)?;
    }
    let mut calls = BTreeMap::<String, BTreeMap<usize, Vec<CallSite>>>::new();
    for site in request.calls {
        calls
            .entry(site.path.clone())
            .or_default()
            .entry(site.line)
            .or_default()
            .push(site);
    }
    let mut declarations = BTreeMap::new();
    for d in request.definitions {
        if matches!(d.kind.as_str(), "function" | "method") {
            record(&mut declarations, d.evidence_id, Some(d.id));
        }
    }
    let mut result = Join::default();
    let mut index = DigestReader {
        source: BufReader::new(regular(index, INDEX_LIMIT)?).take(INDEX_LIMIT + 1),
        digest: Sha256::new(),
        size: 0,
    };
    wire::documents(&mut index, |bytes| {
        result.document(bytes, &manifest, &mut snapshot, &calls, &declarations)
    })?;
    if index.size > INDEX_LIMIT || result.documents.is_empty() {
        return Err("SCIP index has no documents or exceeds its byte limit".to_owned());
    }
    let index_sha256 = format!("{:x}", index.digest.finalize());
    if index_sha256 != manifest.index_sha256 {
        return Err("SCIP index digest does not match its manifest".to_owned());
    }
    let bindings = result
        .references
        .iter()
        .filter_map(|(call_id, symbol)| {
            let anchor = result.targets.get(symbol.as_ref()?)?.as_ref()?;
            Some(Binding { call_id, anchor })
        })
        .collect();
    serde_json::to_vec(&Reply {
        index_sha256,
        manifest_sha256,
        manifest_files: &manifest.files,
        bindings,
    })
    .map_err(|error| error.to_string())
}

fn record<K: Ord, T: Eq>(map: &mut BTreeMap<K, Option<T>>, key: K, value: Option<T>) {
    map.entry(key)
        .and_modify(|prior| {
            if *prior != value {
                *prior = None;
            }
        })
        .or_insert(value);
}

fn doc_header(mut bytes: &[u8]) -> Result<(&str, Option<&[u8]>)> {
    let mut path = None;
    let mut encoding = None;
    let mut embedded = None;
    while !bytes.is_empty() {
        match wire::field(&mut bytes)? {
            (1, Field::Bytes(p)) if path.is_none() => {
                path = Some(std::str::from_utf8(p).map_err(|e| e.to_string())?)
            }
            (5, Field::Bytes(t)) if embedded.is_none() => embedded = Some(t),
            (6, Field::Number(n)) if encoding.is_none() => encoding = Some(n),
            (1 | 5 | 6, _) => return Err("duplicate or invalid SCIP document field".to_owned()),
            _ => (),
        }
    }
    if encoding != Some(1) {
        return Err("SCIP document must use UTF-8 byte positions".to_owned());
    }
    Ok((path.ok_or("SCIP document needs a path")?, embedded))
}

impl<'a> Join<'a> {
    fn document(
        &mut self,
        mut bytes: &[u8],
        manifest: &Manifest,
        snapshot: &mut Snapshot,
        calls: &'a BTreeMap<String, BTreeMap<usize, Vec<CallSite>>>,
        declarations: &'a BTreeMap<String, Option<String>>,
    ) -> Result<()> {
        let (path, embedded) = doc_header(bytes)?;
        if !self.documents.insert(path.to_owned()) || self.documents.len() > SOURCE_LIMIT {
            return Err("duplicate SCIP document or document count exceeded".to_owned());
        }
        let expected = manifest
            .files
            .get(path)
            .ok_or_else(|| format!("unbound SCIP document: {path}"))?;
        let source = source_bytes(snapshot, path, expected)?;
        if embedded.is_some_and(|t| !t.is_empty() && t != source) {
            return Err(format!("SCIP document text differs from source: {path}"));
        }
        let text = std::str::from_utf8(&source).map_err(|error| error.to_string())?;
        let anchors = syntax::source(path, text, calls.get(path), declarations)?;
        while !bytes.is_empty() {
            let (2, Field::Bytes(payload)) = wire::field(&mut bytes)? else {
                continue;
            };
            self.occurrences += 1;
            if self.occurrences > OCCURRENCE_LIMIT {
                return Err("SCIP occurrence limit exceeded".to_owned());
            }
            let occurrence = wire::occurrence(payload)?;
            self.occurrence(path, occurrence, &anchors);
        }
        Ok(())
    }

    fn occurrence(
        &mut self,
        path: &str,
        occurrence: wire::Occurrence<'_>,
        anchors: &syntax::Source<'a>,
    ) {
        let Some(range) = occurrence.range else {
            return;
        };
        if occurrence.symbol.is_empty() || occurrence.symbol.starts_with("local ") {
            return;
        }
        if occurrence.definition {
            let found = anchors
                .definitions
                .get(&range)
                .map(|(id, evidence)| Anchor {
                    target_definition_id: (*id).to_owned(),
                    evidence_id: evidence.clone(),
                    path: path.to_owned(),
                    line: range.0[0].saturating_add(1),
                });
            record(&mut self.targets, occurrence.symbol.to_owned(), found);
        } else if let Some(id) = anchors
            .calls
            .get(&range)
            .filter(|ids| ids.len() == 1)
            .and_then(BTreeSet::first)
        {
            record(&mut self.references, id, Some(occurrence.symbol.to_owned()));
        }
    }
}

struct DigestReader<T> {
    source: T,
    digest: Sha256,
    size: u64,
}

impl<T: Read> Read for DigestReader<T> {
    fn read(&mut self, bytes: &mut [u8]) -> std::io::Result<usize> {
        let count = self.source.read(bytes)?;
        self.digest.update(&bytes[..count]);
        self.size += count as u64;
        Ok(count)
    }
}
