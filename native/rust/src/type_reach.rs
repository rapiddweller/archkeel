// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The check that compiler type-reach facts belong to this scan (AD-1047).
//!
//! The rustc driver writes one JSON-lines file for each Cargo unit and configuration. The first line
//! is a `build` record: the schema number, the text of `rustc -vV`, the SHA-256 of the driver source,
//! the target triple, the configuration, the SHA-256 of `Cargo.lock`, and the SHA-256 that rustc made of
//! each source file it read. The last line is an `end` record with the number of lines before it.
//! This module reads these two lines. A later stage reads the other records.
//!
//! Cargo names the units, and each needs one file. A missing file, a cut-off file, a `--cfg` that is no
//! feature or a hash that differs is a refusal that names the field. A scanned file that no unit read is
//! not a mismatch: it is listed as not built, and its modules keep their gaps. A file that only a test
//! unit read is listed too, because its `cfg(not(test))` code is not seen.

use crate::type_reach_facts::Facts;
use archkeel_facts::envelope::TypeReach;
use archkeel_facts::type_reach::{Config, Field, Unavailable, ENV};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// The binding that the scan expects of every unit of one configuration.
pub struct Expected<'a> {
    /// The text of `rustc -vV` of the pinned toolchain.
    pub rustc: &'a str,
    /// The SHA-256 of the driver source.
    pub driver_sha256: &'a str,
    /// The target triple of the build.
    pub target_triple: &'a str,
    /// The configuration of the facts.
    pub config: &'a Config,
    /// The SHA-256 of `Cargo.lock`.
    pub cargo_lock_sha256: &'a str,
    /// The units that `cargo check` reported: each needs one facts file `<unit>.jsonl`.
    pub units: &'a [String],
    /// The directory of each workspace member, relative to the scan root, with a closing slash. A facts file
    /// that lists a scanned source file under none of them read the code of a crate that is no member.
    pub members: &'a [String],
}

/// What a successful check found.
pub struct Verified {
    /// The number of units.
    pub units: usize,
    /// Scanned files that no unit read, in path order.
    pub not_built: Vec<String>,
    /// Scanned files that only a test unit read: their `cfg(not(test))` code is not seen.
    pub test_only: Vec<String>,
    /// Files that rustc read and the scan did not list, for example generated into `OUT_DIR`.
    pub outside_scan: usize,
}

/// The files that the units read: all units, and the units that are no test build.
struct Built {
    any: BTreeSet<String>,
    plain: BTreeSet<String>,
}

/// The schema number of the facts files. The driver writes the same number.
const SCHEMA: u64 = 1;

impl Expected<'_> {
    /// Check the facts of each expected unit against the scan. `files` pairs a unit with the text of
    /// its file; a file of another unit is ignored. `scanned` maps the path of each scanned `.rs`
    /// file to its SHA-256.
    pub fn verify(
        &self,
        files: &[(String, String)],
        scanned: &BTreeMap<String, String>,
    ) -> Result<Verified, Unavailable> {
        verify(files, self, scanned)
    }

    /// Read the file `<unit>.jsonl` of each expected unit from `dir`, then check them.
    pub fn verify_dir(
        &self,
        dir: &Path,
        scanned: &BTreeMap<String, String>,
    ) -> Result<Verified, Unavailable> {
        let mut files = Vec::new();
        for unit in self.units {
            let text = std::fs::read_to_string(dir.join(format!("{unit}.jsonl")))
                .map_err(|_| mismatch(Field::Unit(unit.clone())))?;
            files.push((unit.clone(), text));
        }
        verify(&files, self, scanned)
    }
}

fn mismatch(field: Field) -> Unavailable {
    Unavailable::BindingMismatch(field)
}

fn same(build: &Value, key: &str, want: &str, field: Field) -> Result<(), Unavailable> {
    match build.get(key).and_then(Value::as_str) {
        Some(got) if got.trim() == want.trim() => Ok(()),
        _ => Err(mismatch(field)),
    }
}

/// One `[path, sha256]` pair of the `files` list.
fn pair(entry: &Value) -> Option<(&str, &str)> {
    let row = entry.as_array()?;
    Some((row.first()?.as_str()?, row.get(1)?.as_str()?))
}

/// The last line is `{"k":"end","lines":N}` and N lines come before it: the file is not cut off.
fn complete(unit: &str, text: &str) -> Result<(), Unavailable> {
    let lines: Vec<&str> = text.lines().collect();
    let end: Option<Value> = lines
        .last()
        .and_then(|line| serde_json::from_str(line).ok());
    let counted = end
        .filter(|end| end.get("k").and_then(Value::as_str) == Some("end"))
        .and_then(|end| end.get("lines").and_then(Value::as_u64));
    match counted {
        Some(count) if count + 1 == lines.len() as u64 => Ok(()),
        _ => Err(mismatch(Field::End(unit.to_string()))),
    }
}

/// Every `--cfg` of the build is a Cargo feature: no flag of another source made the cfg.
fn features_only(build: &Value) -> Result<(), Unavailable> {
    let cfgs = build.get("cfg_args").and_then(Value::as_array);
    let clean = cfgs.is_some_and(|all| {
        all.iter().all(|cfg| {
            cfg.as_str()
                .is_some_and(|text| text.starts_with("feature="))
        })
    });
    if clean {
        Ok(())
    } else {
        Err(mismatch(Field::CfgArgs))
    }
}

fn check_unit(
    (unit, text): (&str, &str),
    want: &Expected<'_>,
    scanned: &BTreeMap<String, String>,
    built: &mut Built,
) -> Result<(), Unavailable> {
    complete(unit, text)?;
    let line = text.lines().next().unwrap_or_default();
    let build: Value = serde_json::from_str(line).map_err(|_| mismatch(Field::Build))?;
    if build.get("k").and_then(Value::as_str) != Some("build") {
        return Err(mismatch(Field::Build));
    }
    if build.get("schema").and_then(Value::as_u64) != Some(SCHEMA) {
        return Err(mismatch(Field::Schema));
    }
    same(&build, "unit", unit, Field::Unit(unit.to_string()))?;
    same(&build, "rustc", want.rustc, Field::Rustc)?;
    same(
        &build,
        "driver_sha256",
        want.driver_sha256,
        Field::DriverSha256,
    )?;
    same(
        &build,
        "target_triple",
        want.target_triple,
        Field::TargetTriple,
    )?;
    same(&build, "cfg", &want.config.cfg_name(), Field::Cfg)?;
    same(
        &build,
        "cargo_lock_sha256",
        want.cargo_lock_sha256,
        Field::CargoLockSha256,
    )?;
    features_only(&build)?;
    let test = build.get("test").and_then(Value::as_bool).unwrap_or(false);
    let files = build
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| mismatch(Field::Build))?;
    for entry in files {
        let (path, sha) = pair(entry).ok_or_else(|| mismatch(Field::Build))?;
        if scanned.contains_key(path)
            && !want
                .members
                .iter()
                .any(|dir| path.starts_with(dir.as_str()))
        {
            return Err(mismatch(Field::NonMember(path.to_string())));
        }
        if scanned.get(path).is_some_and(|scan| scan != sha) {
            return Err(mismatch(Field::SourceFile(path.to_string())));
        }
        built.any.insert(path.to_string());
        if !test {
            built.plain.insert(path.to_string());
        }
    }
    Ok(())
}

fn verify(
    files: &[(String, String)],
    want: &Expected<'_>,
    scanned: &BTreeMap<String, String>,
) -> Result<Verified, Unavailable> {
    if want.units.is_empty() {
        return Err(mismatch(Field::Build));
    }
    let mut built = Built {
        any: BTreeSet::new(),
        plain: BTreeSet::new(),
    };
    for unit in want.units {
        let found = files.iter().find(|(name, _)| name == unit);
        let (name, text) = found.ok_or_else(|| mismatch(Field::Unit(unit.clone())))?;
        check_unit((name, text), want, scanned, &mut built)?;
    }
    let not_built = scanned
        .keys()
        .filter(|path| !built.any.contains(*path))
        .cloned()
        .collect();
    let test_only = scanned
        .keys()
        .filter(|path| built.any.contains(*path) && !built.plain.contains(*path))
        .cloned()
        .collect();
    let outside_scan = built
        .any
        .iter()
        .filter(|path| !scanned.contains_key(*path))
        .count();
    Ok(Verified {
        units: want.units.len(),
        not_built,
        test_only,
        outside_scan,
    })
}

/// The facts of the producer and their provenance, or the cause why a scan that asked has none.
pub type Announced = Option<Result<(Vec<Facts>, TypeReach), String>>;

/// The facts that the producer announced in the descriptor that `ARCHKEEL_TYPE_REACH` names, checked
/// against the scan, with their provenance. `None` when the variable is unset: the scan asks for no facts.
/// `scanned` is read only when the variable is set. An `Err` is the exact cause, and the scan keeps every gap.
pub fn announced(scanned: impl FnOnce() -> BTreeMap<String, String>) -> Announced {
    let path = std::env::var_os(ENV)?;
    Some(read_descriptor(Path::new(&path), &scanned()))
}

fn read_descriptor(
    path: &Path,
    scanned: &BTreeMap<String, String>,
) -> Result<(Vec<Facts>, TypeReach), String> {
    let text =
        std::fs::read_to_string(path).map_err(|e| format!("cannot read the descriptor: {e}"))?;
    let descriptor: Value =
        serde_json::from_str(&text).map_err(|e| format!("the descriptor is no JSON: {e}"))?;
    if let Some(why) = descriptor.get("unavailable").and_then(Value::as_str) {
        return Err(why.to_string());
    }
    let word = |key: &str| {
        descriptor
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    };
    let mut all = Vec::new();
    let mut names = Vec::new();
    let members: Vec<String> = descriptor
        .get("members")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|m| m.as_str().map(str::to_string))
        .collect();
    for entry in descriptor
        .get("configs")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let field = |key: &str| {
            entry
                .get(key)
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string()
        };
        let config = Config::named(&field("name"))
            .ok_or_else(|| "the descriptor names an unknown configuration".to_string())?;
        let units: Vec<String> = entry
            .get("units")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(|u| u.as_str().map(str::to_string))
            .collect();
        let (rustc, driver, triple, lock) = (
            word("rustc"),
            word("driver_sha256"),
            word("target_triple"),
            word("cargo_lock_sha256"),
        );
        let want = Expected {
            rustc: &rustc,
            driver_sha256: &driver,
            target_triple: &triple,
            config: &config,
            cargo_lock_sha256: &lock,
            units: &units,
            members: &members,
        };
        let dir = field("dir");
        names.push(config.cfg_name());
        want.verify_dir(Path::new(&dir), scanned)
            .map_err(|e| e.describe())?;
        all.push(
            Facts::load_dir(Path::new(&dir))
                .ok_or_else(|| "the facts cannot be read".to_string())?,
        );
    }
    if all.is_empty() {
        return Err("the descriptor names no configuration".to_string());
    }
    let fact = TypeReach {
        rustc: word("rustc"),
        target_triple: word("target_triple"),
        driver_sha256: word("driver_sha256"),
        cargo_lock_sha256: word("cargo_lock_sha256"),
        members,
        configs: names,
    };
    Ok((all, fact))
}

#[cfg(test)]
#[path = "type_reach_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "type_reach_real_tests.rs"]
mod real_tests;
