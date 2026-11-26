// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The cause when the compiler type-reach facts are not available, and the configs of the matrix (AD-1047).
//!
//! The values are plain: no derive and no trait impl, only inherent methods (a `Copy` value would need a `Clone` impl). A reply that carries them
//! gets its wire form in a later stage.

/// The environment variable that names the descriptor of the facts for the Rust worker (AD-1047).
pub const ENV: &str = "ARCHKEEL_TYPE_REACH";

/// The environment variable that gives the Rust worker the Cargo workspace members of the scan (#1989). The
/// worker starts no process, so the core runs `cargo metadata` and passes its answer as JSON text.
pub const MEMBERS_ENV: &str = "ARCHKEEL_WORKSPACE_MEMBERS";

/// The name of the contract premise that the use of the facts needs. The contract crate has the same word
/// (`premise_word`); a test of the model crate holds them equal.
pub const PREMISE: &str = "rust_type_reach";

/// The most features, over all workspace members, that the matrix covers one by one. A workspace with more
/// features gets no facts: the producer never drops a configuration silently.
pub const MAX_FEATURES: usize = 16;

/// One Cargo configuration of the matrix that the facts cover.
pub enum Config {
    /// No feature flag.
    Default,
    /// `--no-default-features`.
    NoDefaultFeatures,
    /// `--all-features`.
    AllFeatures,
    /// `--no-default-features --features <package>/<feature>`: one feature alone.
    Feature {
        /// The package of the workspace that has the feature.
        package: String,
        /// The name of the feature.
        feature: String,
    },
}

/// The three fixed configurations, in the order that the producer runs them. Each feature alone follows.
pub fn matrix() -> [Config; 3] {
    [
        Config::Default,
        Config::NoDefaultFeatures,
        Config::AllFeatures,
    ]
}

impl Config {
    /// The name that the driver writes in the `cfg` field of a `build` line.
    pub fn cfg_name(&self) -> String {
        match self {
            Config::Default => "default".to_string(),
            Config::NoDefaultFeatures => "no-default-features".to_string(),
            Config::AllFeatures => "all-features".to_string(),
            Config::Feature { package, feature } => format!("feature:{package}/{feature}"),
        }
    }

    /// The configuration of a name that `cfg_name` gave.
    pub fn named(name: &str) -> Option<Config> {
        if let Some(found) = matrix().into_iter().find(|c| c.cfg_name() == name) {
            return Some(found);
        }
        let (package, feature) = name.strip_prefix("feature:")?.split_once('/')?;
        Some(Config::Feature {
            package: package.to_string(),
            feature: feature.to_string(),
        })
    }

    /// A name that is safe as a directory name.
    pub fn dir_name(&self) -> String {
        self.cfg_name().replace([':', '/'], "_")
    }
}

/// The part of the binding that a check found different.
pub enum Field {
    /// The first line of a facts file is not a `build` record, or there is no facts file.
    Build,
    /// The `schema` number is not one that this reader knows.
    Schema,
    /// The text of `rustc -vV`.
    Rustc,
    /// The SHA-256 of the driver source.
    DriverSha256,
    /// The target triple.
    TargetTriple,
    /// The name of the configuration.
    Cfg,
    /// The SHA-256 of `Cargo.lock`.
    CargoLockSha256,
    /// A `--cfg` that is no Cargo feature: the facts are of another configuration.
    CfgArgs,
    /// An expected unit has no facts file, or its file names another unit. It holds the unit.
    Unit(String),
    /// A facts file has no `end` record, or the count of the `end` record is wrong. It holds the unit.
    End(String),
    /// A facts file names a source file under no workspace member (a path dependency that is no member). It holds the path.
    NonMember(String),
    /// A scanned source file whose hash differs from the one that rustc read. It holds the path.
    SourceFile(String),
}

impl Field {
    /// The field as a short text.
    pub fn describe(&self) -> String {
        match self {
            Field::Build => "build".to_string(),
            Field::Schema => "schema".to_string(),
            Field::Rustc => "rustc".to_string(),
            Field::DriverSha256 => "driver_sha256".to_string(),
            Field::TargetTriple => "target_triple".to_string(),
            Field::Cfg => "cfg".to_string(),
            Field::CargoLockSha256 => "cargo_lock_sha256".to_string(),
            Field::CfgArgs => "cfg_args".to_string(),
            Field::Unit(unit) => format!("unit {unit}"),
            Field::End(unit) => format!("end of unit {unit}"),
            Field::NonMember(path) => format!("file {path} is of no workspace member"),
            Field::SourceFile(path) => format!("file {path}"),
        }
    }
}

/// Why no type-reach facts exist for a scan. Each cause keeps every gap of the syntax scan.
pub enum Unavailable {
    /// The pinned toolchain is not installed.
    ToolchainMissing,
    /// The pinned toolchain has no `rustc-dev` component.
    RustcDevMissing,
    /// The driver did not build.
    DriverBuildFailed,
    /// `cargo check` failed in this configuration.
    CargoCheckFailed(Config),
    /// A facts file does not match the scan.
    BindingMismatch(Field),
    /// The workspace members have this many features: more than `MAX_FEATURES`, so no configuration is dropped silently.
    TooManyFeatures(usize),
    /// `cargo metadata` failed or named no workspace member.
    MetadataFailed,
}

impl Unavailable {
    /// One sentence that names the exact cause.
    pub fn describe(&self) -> String {
        match self {
            Unavailable::ToolchainMissing => {
                "the pinned Rust toolchain is not installed".to_string()
            }
            Unavailable::RustcDevMissing => {
                "the pinned Rust toolchain has no rustc-dev component".to_string()
            }
            Unavailable::DriverBuildFailed => "the rustc driver did not build".to_string(),
            Unavailable::CargoCheckFailed(config) => {
                format!(
                    "cargo check failed in the {} configuration",
                    config.cfg_name()
                )
            }
            Unavailable::TooManyFeatures(count) => format!(
                "the workspace members have {count} features: the matrix covers each feature alone up to {MAX_FEATURES}"
            ),
            Unavailable::MetadataFailed => "cargo metadata failed for the workspace".to_string(),
            Unavailable::BindingMismatch(field) => {
                format!("the facts do not match the scan: {}", field.describe())
            }
        }
    }
}
