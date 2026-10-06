# AD-7 Determinism is measured, not assumed

One observation depends on source bytes at a commit, contract bytes, analyzer and checker digests,
`archkeel.toml`, Python version and repository directory name. Output bytes must not
depend on other environment values.

Three `report` runs on two clones vary parent paths, working directories,
`PYTHONHASHSEED`, `TZ` and `LC_ALL`; a fourth repeats one run verbatim.
`architecture.json`, HTML and stdout JSON must match byte for byte. Normalization
would hide a violation. This probe covers one machine and Python build, not other
versions, operating systems or unvaried inputs.

Check: `tests/test_determinism.py`. An unsorted record subject list and an absolute
source path each fail it.
