// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The contained reads and the work budget of the survey (AD-406, #1099).

use std::path::PathBuf;

use super::*;

#[test]
fn only_a_safe_absolute_disk_path_has_a_plain_form() {
    for (text, expected) in [
        (r"{drive}\repo", Some(r"{drive}\repo")),
        (r"\\?\{drive}\repo", Some(r"{drive}\repo")),
        (r"\\?\{lower}\repo", Some(r"{lower}\repo")),
        (r"\\?\{drive}\", Some(r"{drive}\")),
        (r"\\server\share", None),
        (r"\\?\UNC\server\share", None),
        (r"\\.\{drive}\repo", None),
        (r"\\?\Volume{abc}\repo", None),
        (r"\\?\GLOBALROOT\Device\HarddiskVolume1", None),
        (r"{drive}repo", None),
        (r"{drive}/repo", None),
        (r"{drive}\repo\", None),
        (r"\\?\{drive}\repo\..\other", None),
        (r"\\?\{drive}\repo\.", None),
        (r"\\?\{drive}\repo.", None),
        (r"\\?\{drive}\repo ", None),
        (r"\\?\{drive}\NUL.txt", None),
        (r"\\?\{drive}\COM1", None),
        (r"\\?\{drive}\LPT²", None),
        (r"\\?\{drive}\repo:stream", None),
        (r"\\?\{drive}\repo/other", None),
        (r"\\?\{drive}\repo\\other", None),
    ] {
        let expand = |value: &str| value.replace("{drive}", "C:").replace("{lower}", "c:");
        let text = expand(text);
        let expected = expected.map(expand);
        assert_eq!(disk_text(&text), expected.as_deref(), "{text}");
    }
}

/// A fresh directory below the temporary directory, canonical.
pub(crate) fn scratch(name: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let next = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!(
        "archkeel-collect-{name}-{}-{next}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    local_path(&fs::canonicalize(path).unwrap()).unwrap()
}

#[test]
fn a_root_must_be_absolute_canonical_and_a_directory() {
    let base = scratch("root");
    assert!(Root::of(base.to_str().unwrap()).is_ok());
    assert!(Root::of("relative")
        .unwrap_err()
        .contains("not an absolute path"));
    let dotted = format!("{}/.", base.display());
    assert!(Root::of(&dotted).unwrap_err().contains("not canonical"));
    fs::write(base.join("file"), "x").unwrap();
    let file = base.join("file");
    assert!(Root::of(file.to_str().unwrap())
        .unwrap_err()
        .contains("not a directory"));
}

#[cfg(windows)]
#[test]
fn windows_disk_roots_and_contained_reads_share_the_real_canonical_form() {
    let base = scratch("disk-root");
    let verbatim = fs::canonicalize(&base).unwrap();
    assert!(
        matches!(verbatim.components().next(), Some(Component::Prefix(prefix))
        if matches!(prefix.kind(), std::path::Prefix::VerbatimDisk(_)))
    );
    for path in [&base, &verbatim] {
        let root = Root::of(path.to_str().unwrap()).unwrap();
        assert_eq!(root.path(), base);
        fs::write(base.join("inside.json"), "{}").unwrap();
        assert_eq!(
            root.read("inside.json", 10),
            Ok(Some(("inside.json".into(), b"{}".to_vec())))
        );
    }
    for text in [
        format!("{}\\", base.display()),
        base.to_str().unwrap().replace('\\', "/"),
    ] {
        assert!(Root::of(&text).is_err(), "{text}");
    }
}

#[cfg(windows)]
#[test]
fn windows_disk_junctions_cannot_change_the_root_or_escape_it() {
    let base = scratch("disk-junction");
    let project = base.join("project");
    let outside = base.join("outside");
    fs::create_dir(&project).unwrap();
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("secret.json"), "{}").unwrap();
    let link = project.join("link");
    let done = std::process::Command::new("cmd")
        .args(["/C", "mklink", "/J"])
        .arg(&link)
        .arg(&outside)
        .output()
        .unwrap();
    assert!(done.status.success(), "{done:?}");
    assert!(Root::of(link.to_str().unwrap())
        .unwrap_err()
        .contains("not canonical"));
    let root = Root::of(project.to_str().unwrap()).unwrap();
    assert_eq!(root.contained("link/secret.json"), None);
    assert_eq!(root.read("link/secret.json", 10), Ok(None));
    fs::remove_dir(link).unwrap();
    fs::remove_dir_all(base).unwrap();
}

#[cfg(unix)]
#[test]
fn a_symlink_root_stays_noncanonical() {
    let base = scratch("linked-root");
    fs::create_dir(base.join("real")).unwrap();
    std::os::unix::fs::symlink(base.join("real"), base.join("link")).unwrap();
    assert!(Root::of(base.join("link").to_str().unwrap())
        .unwrap_err()
        .contains("not canonical"));
}

#[test]
fn a_read_outside_the_root_gives_no_bytes() {
    let base = scratch("outside");
    let root_path = base.join("repo");
    fs::create_dir_all(root_path.join("sub")).unwrap();
    fs::write(base.join("secret.json"), "{}").unwrap();
    fs::write(root_path.join("sub/in.json"), "{\"a\":1}").unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink(base.join("secret.json"), root_path.join("link.json")).unwrap();
    let root = Root::of(root_path.to_str().unwrap()).unwrap();
    assert_eq!(root.read("../secret.json", 100), Ok(None));
    assert_eq!(
        root.read(base.join("secret.json").to_str().unwrap(), 100),
        Ok(None)
    );
    #[cfg(unix)]
    assert_eq!(root.read("link.json", 100), Ok(None));
    assert_eq!(root.read("sub", 100), Ok(None));
    assert_eq!(
        root.read("sub/../sub/in.json", 100),
        Ok(Some(("sub/in.json".to_owned(), b"{\"a\":1}".to_vec())))
    );
    assert_eq!(
        root.read("sub/in.json", 3),
        Err(Over("sub/in.json".to_owned()))
    );
}

#[test]
fn the_survey_refuses_more_entries_than_the_budget() {
    let base = scratch("entries");
    for directory in 0..=(MAX_ENTRIES / 1000) {
        let path = base.join(format!("d{directory}"));
        fs::create_dir_all(&path).unwrap();
        for file in 0..1000 {
            fs::write(path.join(format!("f{file}.ts")), "").unwrap();
        }
    }
    let root = Root::of(base.to_str().unwrap()).unwrap();
    let started = std::time::Instant::now();
    let refusal = survey(&root).unwrap_err();
    assert!(refusal.contains("more than 100000 entries"), "{refusal}");
    assert!(started.elapsed().as_secs() < 30);
    // AD-432: the entries below a proven cache directory have a budget of their own, so the
    // build output of a used checkout does not use the budget of the source.
    for directory in ["d0", "d1"] {
        fs::write(base.join(directory).join(CACHE_TAG), CACHE_SIGNATURE).unwrap();
    }
    assert_eq!(survey(&root), Ok(()));
    // The budget of the cache directories is a limit too: 2002 entries are below the two tags.
    assert_eq!(survey_within(&root, 2002), Ok(()));
    let refusal = survey_within(&root, 2001).unwrap_err();
    assert!(
        refusal.contains("more than 2001 entries below its cache directories"),
        "{refusal}"
    );
    // The source budget holds beside a cache directory: one more source directory is refused.
    let more = base.join("more");
    fs::create_dir_all(&more).unwrap();
    for file in 0..1100 {
        fs::write(more.join(format!("f{file}.ts")), "").unwrap();
    }
    let refusal = survey(&root).unwrap_err();
    assert!(refusal.contains("more than 100000 entries"), "{refusal}");
    let _ = fs::remove_dir_all(base);
}

/// A project with one file over the byte total in `target/debug`; the file has no data blocks.
fn with_large_build_output(name: &str) -> (PathBuf, Root) {
    let base = scratch(name);
    fs::create_dir_all(base.join("target/debug")).unwrap();
    fs::write(base.join("lib.rs"), "pub fn a() {}\n").unwrap();
    let large = fs::File::create(base.join("target/debug/large.rlib")).unwrap();
    large.set_len(MAX_TOTAL_BYTES + 1).unwrap();
    let root = Root::of(base.to_str().unwrap()).unwrap();
    (base, root)
}

#[test]
fn the_survey_charges_no_bytes_below_a_proven_cache_directory() {
    let (base, root) = with_large_build_output("cache");
    let refusal = survey(&root).unwrap_err();
    assert!(
        refusal.contains("holds more than 1073741824 bytes"),
        "{refusal}"
    );
    let mut tag = CACHE_SIGNATURE.to_vec();
    tag.extend_from_slice(b"\n# This file is a cache directory tag created by cargo.\n");
    fs::write(base.join("target").join(CACHE_TAG), tag).unwrap();
    assert_eq!(survey(&root), Ok(()));
    // The bytes of a file outside the cache directory are charged as before.
    let outside = fs::File::create(base.join("large.bin")).unwrap();
    outside.set_len(MAX_TOTAL_BYTES + 1).unwrap();
    assert!(survey(&root).unwrap_err().contains("holds more than"));
    let _ = fs::remove_dir_all(base);
}

#[test]
fn a_tag_without_the_signature_or_behind_a_link_proves_no_cache_directory() {
    let (base, root) = with_large_build_output("no-cache");
    let tag = base.join("target").join(CACHE_TAG);
    for text in [
        "",
        "Signature: 0",
        "# Signature: 8a477f597d28d172789f06886806bc55",
    ] {
        fs::write(&tag, text).unwrap();
        assert!(
            survey(&root).unwrap_err().contains("holds more than"),
            "{text}"
        );
    }
    fs::remove_file(&tag).unwrap();
    fs::create_dir(&tag).unwrap();
    assert!(survey(&root).unwrap_err().contains("holds more than"));
    fs::remove_dir(&tag).unwrap();
    #[cfg(unix)]
    {
        fs::write(base.join("real.tag"), CACHE_SIGNATURE).unwrap();
        std::os::unix::fs::symlink(base.join("real.tag"), &tag).unwrap();
        assert!(survey(&root).unwrap_err().contains("holds more than"));
    }
    // A tag in a sibling directory or below the build output proves nothing about the output.
    let _ = fs::remove_file(&tag);
    fs::create_dir_all(base.join("other")).unwrap();
    fs::write(base.join("other").join(CACHE_TAG), CACHE_SIGNATURE).unwrap();
    fs::create_dir_all(base.join("target/debug/deps")).unwrap();
    fs::write(
        base.join("target/debug/deps").join(CACHE_TAG),
        CACHE_SIGNATURE,
    )
    .unwrap();
    assert!(survey(&root).unwrap_err().contains("holds more than"));
    let _ = fs::remove_dir_all(base);
}

#[cfg(unix)]
#[test]
fn a_directory_that_cannot_be_listed_below_a_proven_cache_is_no_refusal() {
    use std::os::unix::fs::PermissionsExt;

    let (base, root) = with_large_build_output("cache-gone");
    fs::write(base.join("target").join(CACHE_TAG), CACHE_SIGNATURE).unwrap();
    fs::create_dir_all(base.join("target/debug/deps/rustcX")).unwrap();
    fs::create_dir_all(base.join("src/locked")).unwrap();
    let locked = [
        base.join("target/debug/deps/rustcX"),
        base.join("src/locked"),
    ];
    for path in &locked {
        fs::set_permissions(path, fs::Permissions::from_mode(0o000)).unwrap();
    }
    // A process that is allowed to read it (root) cannot show the failure.
    if fs::read_dir(&locked[0]).is_err() {
        // A directory outside the cache stays a refusal: the scan cannot read that source.
        let refusal = survey(&root).unwrap_err();
        assert!(refusal.contains("src/locked"), "{refusal}");
        fs::set_permissions(&locked[1], fs::Permissions::from_mode(0o755)).unwrap();
        // The directory below the proven cache is build output: no refusal.
        assert_eq!(survey(&root), Ok(()));
    }
    for path in &locked {
        fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
    }
    let _ = fs::remove_dir_all(base);
}

#[test]
fn the_survey_refuses_a_deep_nest_and_follows_no_symlink_loop() {
    let base = scratch("deep");
    let mut path = base.clone();
    for _ in 0..=MAX_DEPTH {
        path = path.join("d");
    }
    fs::create_dir_all(&path).unwrap();
    let root = Root::of(base.to_str().unwrap()).unwrap();
    assert!(survey(&root).unwrap_err().contains("deeper than 256"));
    let looped = scratch("loop");
    fs::create_dir_all(looped.join("src")).unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink("..", looped.join("src/up")).unwrap();
    let root = Root::of(looped.to_str().unwrap()).unwrap();
    assert_eq!(survey(&root), Ok(()));
}
