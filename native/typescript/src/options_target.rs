// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The values of `target` and `moduleDetection` (`config.ScriptTarget`, `ModuleDetection`).

/// `target`: every value, because the default libs depend on it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Target {
    Es3,
    Es5,
    Es6,
    Es2015,
    Es2016,
    Es2017,
    Es2018,
    Es2019,
    Es2020,
    Es2021,
    Es2022,
    Es2023,
    Es2024,
    EsNext,
}

impl Target {
    /// Every value.
    const ALL: [Target; 14] = [
        Self::Es3,
        Self::Es5,
        Self::Es6,
        Self::Es2015,
        Self::Es2016,
        Self::Es2017,
        Self::Es2018,
        Self::Es2019,
        Self::Es2020,
        Self::Es2021,
        Self::Es2022,
        Self::Es2023,
        Self::Es2024,
        Self::EsNext,
    ];

    /// The lower-case name of the value, as the compiler and the lib catalog write it.
    pub fn name(self) -> String {
        format!("{self:?}").to_lowercase()
    }
}

/// `moduleDetection`: whether a file without `import` or `export` is a script.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Detection {
    Auto,
    Legacy,
    Force,
}

pub fn target_kind(name: &str) -> Option<Target> {
    Target::ALL.into_iter().find(|target| target.name() == name)
}

pub fn detection_kind(name: &str) -> Option<Detection> {
    let all = [Detection::Auto, Detection::Legacy, Detection::Force];
    all.into_iter()
        .find(|kind| format!("{kind:?}").to_lowercase() == name)
}
