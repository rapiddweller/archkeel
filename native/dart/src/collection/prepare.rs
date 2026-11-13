// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Prepare all selected files before declarations; never discard a source silently.

use super::{file_span, Builder, Stop};
use archkeel_facts::vocab::ExceptionName;
use std::collections::BTreeMap;

impl Builder<'_> {
    pub(super) fn prepare(&mut self) -> Result<(), Stop> {
        for (index, source) in self.input.files.iter().enumerate() {
            self.decl.work.copies(&source.file)?;
            if self
                .by_path
                .insert(source.file.rel.clone(), index)
                .is_some()
            {
                return Err(Stop::Input);
            }
            self.files.push(source.file.clone());
        }
        for source in &self.input.files {
            self.decl.work.charge(1)?;
            let rel = &source.file.rel;
            let syntax = &source.file.syntax;
            if syntax.first_error.is_none() {
                self.parsed.insert(rel.clone());
            } else {
                self.incomplete_paths.insert(rel.clone());
            }
            for (span, kind, message) in crate::records::parse_gaps(syntax) {
                self.decl.work.charge(1)?;
                self.gap(rel, span, kind, message, None)?;
            }
        }
        for problem in &self.input.problems {
            self.decl.work.copies(problem)?;
            self.gap(
                &problem.path,
                &file_span(),
                problem.kind,
                &problem.message,
                None,
            )?;
        }
        let (supported, gaps, work) =
            crate::records::sdk_support(self.input.sdk_state, self.input.sdk.as_deref());
        self.decl.work.charge(work)?;
        self.sdk_supported = supported;
        for gap in gaps {
            self.decl.work.charge(1)?;
            self.decl
                .gaps
                .entry(gap.id.as_str().to_owned())
                .or_insert(gap);
        }
        for source in &self.input.files {
            self.decl.work.charge(1)?;
            let rel = &source.file.rel;
            if !self.parsed.contains(rel) {
                continue;
            }
            match &source.owner {
                None => {
                    self.parsed.remove(rel);
                    self.gap(
                        rel,
                        &file_span(),
                        ExceptionName::PartError,
                        "source has no unique selected library owner",
                        None,
                    )?;
                }
                Some(module) => {
                    self.decl.work.text(module)?;
                    let index = *self.by_path.get(rel).ok_or(Stop::Input)?;
                    self.files
                        .get_mut(index)
                        .ok_or(Stop::Input)?
                        .module
                        .clone_from(module);
                }
            }
        }
        self.language_overrides()
    }

    fn language_overrides(&mut self) -> Result<(), Stop> {
        let mut versions: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
        for source in &self.input.files {
            self.decl.work.text(&source.content)?;
            let rel = &source.file.rel;
            if !self.parsed.contains(rel) {
                continue;
            }
            let Some(raw) = override_text(&source.content, &self.decl.work)? else {
                continue;
            };
            if raw.split('.').any(|part| part.len() > 4_300) {
                self.gap(
                    rel,
                    &file_span(),
                    ExceptionName::LanguageVersionError,
                    "LanguageVersionDigitLimit: Dart language version exceeds 4300 digits",
                    None,
                )?;
                continue;
            }
            let Some(version) = version(raw) else {
                let mut quoted = String::new();
                archkeel_facts::pyrepr::string(raw, &mut quoted);
                self.gap(
                    rel,
                    &file_span(),
                    ExceptionName::LanguageVersionError,
                    &format!("unsupported Dart language version override {quoted}"),
                    None,
                )?;
                continue;
            };
            let module = self.file(rel)?.module.clone();
            versions
                .entry(module)
                .or_default()
                .insert(rel.clone(), version);
        }
        for (module, paths) in versions {
            self.decl.work.copies(&paths)?;
            let mut values = paths.values();
            let first = values.next();
            if values.all(|value| Some(value) == first) {
                continue;
            }
            let main = self.overriding_main(&module, &paths)?;
            let message = if main.is_some() {
                "library parts declare inconsistent Dart language versions"
            } else {
                "LanguageVersionOrderGap: inconsistent parts have no overriding main library"
            };
            let path = main
                .or_else(|| paths.keys().next().cloned())
                .ok_or(Stop::Input)?;
            self.gap(
                &path,
                &file_span(),
                ExceptionName::LanguageVersionError,
                message,
                None,
            )?;
        }
        Ok(())
    }

    fn overriding_main(
        &self,
        module: &str,
        paths: &BTreeMap<String, String>,
    ) -> Result<Option<String>, Stop> {
        for source in &self.input.files {
            self.decl.work.charge(1)?;
            if paths.contains_key(&source.file.rel) && source.file.module == module {
                return Ok(Some(source.file.rel.clone()));
            }
        }
        Ok(None)
    }
}

fn override_text<'a>(
    mut content: &'a str,
    work: &crate::declarations::work::Work,
) -> Result<Option<&'a str>, Stop> {
    while !content.is_empty() {
        work.charge(1)?;
        let line = crate::pytext::lstrip(content);
        let raw = line
            .strip_prefix("//")
            .map(crate::pytext::lstrip)
            .and_then(|rest| rest.strip_prefix("@dart="));
        if let Some(raw) = raw {
            let end = raw.find(crate::pytext::is_space).unwrap_or(raw.len());
            if end > 0 {
                return Ok(raw.get(..end));
            }
        }
        content = line.split_once('\n').map_or("", |(_, rest)| rest);
    }
    Ok(None)
}

fn version(raw: &str) -> Option<String> {
    let parts: Vec<_> = raw.split('.').collect();
    if !(2..=3).contains(&parts.len()) {
        return None;
    }
    let mut canonical = Vec::new();
    for part in parts {
        if part.is_empty() || !part.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        let value = part.trim_start_matches('0');
        canonical.push(if value.is_empty() { "0" } else { value });
    }
    let [major, minor, ..] = canonical.as_slice() else {
        return None;
    };
    let at_least_12 = minor.len() > 2 || (minor.len() == 2 && *minor >= "12");
    let at_most_12 = minor.len() < 2 || (minor.len() == 2 && *minor <= "12");
    if !((*major == "2" && at_least_12) || (*major == "3" && at_most_12)) {
        return None;
    }
    if canonical.len() == 2 {
        canonical.push("0");
    }
    Some(canonical.join("."))
}
