# AD-358 One collector process serves the Python survey and the collection

**Status.** Accepted. Epic #880, host PR 2 (plan change after the interim benchmark, finding 2).

**Decision.**
1. `PythonProviderCollector` starts the Python collector once. It sends one request: phase
   `providers`, wire protocol 8 (9 with test exclusions), and the argument `--one-pass`.
2. With `--one-pass`, `entry.py` calls `complete_collection`. The function runs the survey,
   captures the provider sources and collects with them, all in one process. It then replies with
   the final facts. The reply equals the old final reply: no provider sources travel in it.
3. The checks of the two passes stay. `complete_collection` raises `ProtocolError` when the provider
   inputs differ from the captured sources ("Provider source inputs changed after discovery."),
   when a project input, the analyzer, the runtime or the scope changed between the passes, or when
   a registry alias disagrees with its initializer source (`_provider_pass_problem`).
4. The host checks the reply. `PythonProviderCollector` refuses facts without the full set of
   sections. `check_reply` reads a full reply to a `providers` request as a collection. It takes the
   expected provider sources from the reply itself (`_as_collected` in `reply_checks.py`), so its
   digest comparison cannot fail. The real comparison runs inside the collector (point 3). The
   check that binds each provider binding to one of the listed sources still works. Security is no
   worse than before: the same collector code ran both passes, and the host never had a source of
   its own to compare with.
5. Without `--one-pass` the entry is unchanged: a `providers` request gets the survey and the
   provider sources. The golden `providers` replies stay as they are.
6. `archkeel.cli.studio` holds the Studio command, its stories and its workspace. Only
   `archkeel studio` imports it. The other commands no longer import the HTTP server, the file
   lock and `asyncio`. `cache_folder` and `root_digest` move to `cli/arguments.py`.

**Reason.** The first design started the collector twice, decoded and validated two replies and
built the bindings four times. The second start repeats the process start and the project parse.
One process removes the second start, the second decode and the second validation.

**Rejected.**
- Two requests on one pipe. It needs a framed transport in `process.py`, which host PR 1 changes.
- Provider sources in the final reply. The decoder allows them only with a survey reply, so the
  change would widen the codec in `ir/`.
- A cache of the parsed providers between the two passes. It can change the facts: a facade flag
  set in one pass can be wrong in the next. It is a separate change.

**Limit.** A failed pass check now ends the collector with exit status 1 and its message on stderr,
so the host reports `execution_error` and not `protocol_error`. The provider analysis of the survey
and of the collection still costs most of the time on a project that imports many modules.

**Tests.** `tests/test_python_provider_sources.py`: `test_host_starts_one_collector_for_the_survey_and_the_collection`,
`test_one_pass_collection_without_provider_sources_equals_the_plain_collection`,
`test_one_pass_refuses_a_project_that_changes_between_the_survey_and_the_collection`,
`test_one_pass_refuses_provider_inputs_that_differ_from_the_captured_sources`,
`test_one_pass_refuses_an_unproven_registry_alias`,
`test_reply_check_binds_a_one_pass_reply_to_the_provider_inputs_that_it_lists`,
`test_provider_wrapper_rejects_a_survey_instead_of_final_full_facts`.
