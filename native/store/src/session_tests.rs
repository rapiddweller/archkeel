// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::run;

fn frame(tag: u8, payload: &[u8]) -> Vec<u8> {
    let mut bytes = vec![tag];
    bytes.extend_from_slice(&(payload.len() as u64).to_be_bytes());
    bytes.extend_from_slice(payload);
    bytes
}

/// The answers of `run`: each tag and its text.
fn answers(input: &[u8]) -> Vec<(u8, String)> {
    let mut output = Vec::new();
    let mut reader = input;
    if run(&mut reader, &mut output, 1 << 20).is_err() {
        return Vec::new();
    }
    let mut result = Vec::new();
    let mut rest = output.as_slice();
    while rest.len() >= 9 {
        let mut length = [0u8; 8];
        length.copy_from_slice(&rest[1..9]);
        let end = 9 + usize::try_from(u64::from_be_bytes(length)).unwrap_or(0);
        result.push((rest[0], String::from_utf8_lossy(&rest[9..end]).into_owned()));
        rest = &rest[end..];
    }
    result
}

#[test]
fn a_frame_before_the_reply_is_an_error_answer_and_the_process_goes_on() {
    let mut input = frame(b'B', b"{}");
    input.extend(frame(b'W', b"{}"));
    input.extend(frame(b'R', b"not a reply"));
    let got = answers(&input);
    assert_eq!(got.len(), 3);
    assert!(got.iter().all(|(tag, _)| *tag == b'E'));
    assert!(got[0].1.contains("holds no reply"));
    assert!(got[2].1.contains("only the compressed replies"));
}

#[test]
fn an_unknown_tag_is_an_error_answer() {
    let got = answers(&frame(b'Q', b""));
    assert_eq!(got, vec![(b'E', "unknown frame tag 81".to_owned())]);
}

#[test]
fn a_truncated_frame_ends_the_process_with_an_error() {
    let mut output = Vec::new();
    let input = [b'R', 0, 0, 0, 0, 0, 0, 0, 9, 1];
    assert!(run(&mut input.as_slice(), &mut output, 1 << 20).is_err());
}

#[test]
fn a_bad_observation_frame_is_an_error_answer_and_the_next_frame_is_read() {
    use crate::validate::tests::{compressed, golden};

    let mut input = frame(b'R', &compressed(&golden("h-typescript")));
    input.extend(frame(
        b'W',
        b"{\"texts\": [], \"fields\": {}, \"model\": {\"x\": [1",
    ));
    input.extend(frame(
        b'W',
        b"{\"texts\": [], \"fields\": {}, \"model\": {}, \"more\": 1}",
    ));
    input.extend(frame(b'Q', b""));
    let got = answers(&input);
    let tags: Vec<u8> = got.iter().map(|(tag, _)| *tag).collect();
    assert_eq!(tags, vec![b'O', b'E', b'E', b'E'], "{got:?}");
    assert!(got[2].1.contains("unknown field `more`"), "{}", got[2].1);
    assert_eq!(got[3].1, "unknown frame tag 81");
}
