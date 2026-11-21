// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Prototype reader for explicitly supplied, source-bound SCIP files.

mod bindings;
mod syntax;
mod wire;

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::Path;

use archkeel_facts::identity::{inside, sha256_hex};
use archkeel_snapshot::Snapshot;
use scip_serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use bindings::{record, Matches};
use syntax::CallSite;
use wire::Field;

type Result<T> = std::result::Result<T, String>;
const INDEX_LIMIT: u64 = 64 << 20;
const MANIFEST_LIMIT: u64 = 8 << 20;
const REQUEST_LIMIT: u64 = 16 << 20;
const SOURCE_LIMIT: usize = 4096;
const OCCURRENCE_LIMIT: usize = 512_000;

#[derive(Deserialize)]
#[serde(crate = "scip_serde", deny_unknown_fields)]
struct Manifest {
    version: u32,
    index_sha256: String,
    files: BTreeMap<String, String>,
}

#[derive(Deserialize)]
#[serde(crate = "scip_serde", deny_unknown_fields)]
struct Request {
    calls: Vec<CallSite>,
    definitions: Vec<Definition>,
    #[serde(default)]
    local_packages: Vec<String>,
}

#[derive(Deserialize)]
#[serde(crate = "scip_serde", deny_unknown_fields)]
struct Definition {
    id: String,
    evidence_id: String,
    kind: String,
}

#[derive(Serialize)]
#[serde(crate = "scip_serde")]
struct Header<'a> {
    index_sha256: String,
    manifest_sha256: Option<String>,
    source_files: &'a BTreeMap<String, String>,
}

#[derive(Default)]
struct Join<'a> {
    documents: BTreeSet<String>,
    matches: Matches<'a>,
    occurrences: usize,
}

pub(super) fn run(stack_bytes: usize) -> Result<()> {
    let args = std::env::args().skip(2).collect::<Vec<_>>();
    let (root, index, manifest) = match args.as_slice() {
        [root, index] => (root, index, None),
        [root, index, manifest] => (root, index, Some(manifest.clone())),
        _ => return Err("usage: scip-evidence ROOT INDEX [MANIFEST]".to_owned()),
    };
    let request = bounded_read(&mut std::io::stdin().lock(), REQUEST_LIMIT)?;
    let request: Request = serde_json::from_slice(&request).map_err(|e| e.to_string())?;
    let (root, index) = (root.clone(), index.clone());
    std::thread::Builder::new()
        .stack_size(stack_bytes)
        .spawn(move || {
            archkeel_snapshot::work::bounded(|| {
                let mut output = BufWriter::new(std::io::stdout().lock());
                join(
                    &root,
                    Path::new(&index),
                    manifest.as_deref().map(Path::new),
                    request,
                    &mut output,
                )?;
                output.flush().map_err(|error| error.to_string())
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

fn source_bytes(snapshot: &mut Snapshot, path: &str) -> Result<Vec<u8>> {
    if !inside(path) || snapshot.real(path).as_deref() != Some(path) {
        return Err(format!("invalid SCIP source path: {path}"));
    }
    snapshot
        .read(path)
        .ok_or_else(|| format!("unreadable SCIP source: {path}"))
}

fn read_manifest(path: &Path) -> Result<(String, Manifest)> {
    let raw = bounded_read(&mut regular(path, MANIFEST_LIMIT)?, MANIFEST_LIMIT)?;
    let receipt: Manifest = serde_json::from_slice(&raw).map_err(|error| error.to_string())?;
    if receipt.version != 1 || receipt.files.len() > SOURCE_LIMIT || receipt.files.is_empty() {
        return Err("unsupported SCIP manifest version or file count".to_owned());
    }
    Ok((sha256_hex(&raw), receipt))
}

fn join(
    root: &str,
    index: &Path,
    manifest: Option<&Path>,
    request: Request,
    output: &mut impl Write,
) -> Result<()> {
    let receipt = manifest.map(read_manifest).transpose()?;
    let mut source_files = receipt
        .as_ref()
        .map(|(_, m)| m.files.clone())
        .unwrap_or_default();
    if request.calls.len() > 100_000
        || request.definitions.len() > 100_000
        || request.local_packages.len() > SOURCE_LIMIT
    {
        return Err("SCIP request exceeds its row limit".to_owned());
    }
    let mut snapshot = Snapshot::open_root(root)?;
    for (path, digest) in &source_files {
        let source = source_bytes(&mut snapshot, path)?;
        if sha256_hex(&source) != *digest {
            return Err(format!("stale SCIP source: {path}"));
        }
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
    result.matches.local_packages(request.local_packages);
    let mut index = DigestReader {
        source: BufReader::new(regular(index, INDEX_LIMIT)?).take(INDEX_LIMIT + 1),
        digest: Sha256::new(),
        size: 0,
    };
    wire::documents(&mut index, |bytes| {
        result.document(
            bytes,
            &mut source_files,
            &mut snapshot,
            &calls,
            &declarations,
        )
    })?;
    if index.size > INDEX_LIMIT || result.documents.is_empty() {
        return Err("SCIP index has no documents or exceeds its byte limit".to_owned());
    }
    let index_sha256 = format!("{:x}", index.digest.finalize());
    if receipt
        .as_ref()
        .is_some_and(|(_, m)| m.index_sha256 != index_sha256)
    {
        return Err("SCIP index digest does not match its manifest".to_owned());
    }
    line(
        output,
        &Header {
            index_sha256,
            manifest_sha256: receipt.map(|(digest, _)| digest),
            source_files: &source_files,
        },
    )?;
    for call in calls.values().flat_map(BTreeMap::values).flatten() {
        line(output, &result.matches.bind(call))?;
    }
    Ok(())
}

fn line(output: &mut impl Write, value: &impl Serialize) -> Result<()> {
    serde_json::to_writer(&mut *output, value).map_err(|error| error.to_string())?;
    output.write_all(b"\n").map_err(|error| error.to_string())
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
        source_files: &mut BTreeMap<String, String>,
        snapshot: &mut Snapshot,
        calls: &'a BTreeMap<String, BTreeMap<usize, Vec<CallSite>>>,
        declarations: &'a BTreeMap<String, Option<String>>,
    ) -> Result<()> {
        let (path, embedded) = doc_header(bytes)?;
        if !self.documents.insert(path.to_owned()) || self.documents.len() > SOURCE_LIMIT {
            return Err("duplicate SCIP document or document count exceeded".to_owned());
        }
        let source = source_bytes(snapshot, path)?;
        let digest = sha256_hex(&source);
        let expected = source_files.get(path);
        if expected.is_some_and(|known| known != &digest) {
            return Err(format!("stale SCIP source: {path}"));
        }
        match embedded {
            Some(text) if text != source => {
                return Err(format!("SCIP document text differs from source: {path}"))
            }
            None if expected.is_none() => {
                return Err(format!("unbound or stale SCIP document: {path}"))
            }
            _ => (),
        }
        source_files.insert(path.to_owned(), digest);
        if source_files.len() > SOURCE_LIMIT {
            return Err("SCIP source count exceeded".to_owned());
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
            self.matches.occurrence(path, occurrence, &anchors);
        }
        Ok(())
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
