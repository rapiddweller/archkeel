# AD-1035: Report skipped draft files

Status: accepted.

The draft can skip an existing contract and its page. The init block names the
files written and the draft files skipped. When it skips a file, it does not
claim that it created every configuration and contract of a mixed project.
The JSON init result carries the same skipped paths. The writer still refuses
to replace an existing file.

`tests/test_cli_init_outcome.py` checks a mixed draft and an existing contract.
