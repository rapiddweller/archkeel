// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Rust collector is an installed sibling executable, never a program selected by the project.

use crate::refusal::{refused, Refusal, RefusalKind};
use archkeel_facts::envelope::Reply;
use archkeel_wire::worker::{read_rust_v1, RUST_WORKER_V1};
use std::io::Write;
use std::process::{Command, Stdio};

pub(crate) fn executable() -> std::io::Result<std::path::PathBuf> {
    let exe = std::env::current_exe()?;
    // A test binary is `target/<profile>/deps/<name>`; `cargo build -p archkeel-rust-collector` puts the worker in `target/<profile>`.
    #[cfg(test)]
    let exe = exe
        .parent()
        .and_then(|dir| dir.parent())
        .ok_or(std::io::ErrorKind::NotFound)?
        .join("archkeel-core");
    Ok(exe.with_file_name(format!(
        "archkeel-rust-collector{}",
        std::env::consts::EXE_SUFFIX
    )))
}

pub(crate) fn read(request: &[u8]) -> Result<Reply, Refusal> {
    let io = |e: std::io::Error| refused("Rust worker", e.to_string());
    let worker = executable().map_err(io)?;
    let mut cmd = Command::new(&worker);
    cmd.env_clear();
    #[cfg(windows)]
    if let Some(root) = std::env::var_os("SystemRoot") {
        cmd.env("SystemRoot", root);
    }
    let mut child = cmd
        .arg(RUST_WORKER_V1)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| refused("Rust worker", format!("{}: {e}", worker.display())))?;
    let exchange = (|| {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| refused("Rust worker", "missing stdin"))?;
        stdin
            .write_all(request)
            .and_then(|()| stdin.write_all(b"\n"))
            .map_err(io)?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| refused("Rust worker", "missing stdout"))?;
        read_rust_v1(stdout).map_err(|why| refused("Rust worker", why))
    })();
    if exchange.is_err() {
        let _ = child.kill();
    }
    let status = child.wait().map_err(io)?;
    let result = exchange?;
    if !status.success() {
        return Err(refused(
            "Rust worker",
            format!("worker exited with {status}"),
        ));
    }
    result.map_err(|reason| Refusal {
        kind: RefusalKind::ParseWork,
        part: "parse work",
        reason,
    })
}
