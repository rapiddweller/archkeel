// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A worker is an installed sibling executable, never a program selected by the project.

use crate::refusal::{refused, Refusal, RefusalKind};
use archkeel_facts::envelope::Reply;
use archkeel_wire::worker::{read_rust_v1, RUST_WORKER_V1};
use std::io::Write;
use std::process::{Command, Stdio};

pub(crate) enum Worker {
    Rust,
    TypeScript,
}

pub(crate) fn executable(worker: &Worker) -> std::io::Result<std::path::PathBuf> {
    let exe = std::env::current_exe()?;
    // Cargo puts this crate's test binary under `deps/`, one level below the workers.
    #[cfg(test)]
    let exe = exe
        .parent()
        .and_then(|dir| dir.parent())
        .ok_or(std::io::ErrorKind::NotFound)?
        .join("archkeel-core");
    let name = match worker {
        Worker::Rust => "archkeel-rust-collector",
        Worker::TypeScript => "archkeel-typescript-collector",
    };
    Ok(exe.with_file_name(format!("{name}{}", std::env::consts::EXE_SUFFIX)))
}

pub(crate) fn read(
    worker: Worker,
    request: &[u8],
    facts: Option<&std::path::Path>,
    members: Option<&str>,
) -> Result<Reply, Refusal> {
    let part = match worker {
        Worker::Rust => "Rust worker",
        Worker::TypeScript => "TypeScript worker",
    };
    let for_rust = matches!(worker, Worker::Rust);
    let io = |e: std::io::Error| refused(part, e.to_string());
    let worker = executable(&worker).map_err(io)?;
    let mut cmd = Command::new(&worker);
    cmd.env_clear();
    // AD-1047: the descriptor of the compiler facts, for the Rust worker only.
    if let Some(path) = facts.filter(|_| for_rust) {
        cmd.env(archkeel_facts::type_reach::ENV, path);
    }
    if let Some(text) = members.filter(|_| for_rust) {
        cmd.env(archkeel_facts::type_reach::MEMBERS_ENV, text);
    }
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
        .map_err(|e| refused(part, format!("{}: {e}", worker.display())))?;
    let exchange = (|| {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| refused(part, "missing stdin"))?;
        stdin
            .write_all(request)
            .and_then(|()| stdin.write_all(b"\n"))
            .map_err(io)?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| refused(part, "missing stdout"))?;
        read_rust_v1(stdout).map_err(|why| refused(part, why))
    })();
    if exchange.is_err() {
        let _ = child.kill();
    }
    let status = child.wait().map_err(io)?;
    let result = exchange?;
    if !status.success() {
        return Err(refused(part, format!("worker exited with {status}")));
    }
    result.map_err(|reason| Refusal {
        kind: RefusalKind::ParseWork,
        part: "parse work",
        reason,
    })
}
