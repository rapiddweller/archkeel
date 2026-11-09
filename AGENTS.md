# AGENTS.md

Guidance for coding agents that change Archkeel. People and agents follow the same rules.

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before you change code. It owns the setup, the
  pre-push gate, the decision-record rule and the writing standard.
- Keep agent plans, working specs and evidence out of the repository. A final checked story may
  live at `.archkeel/stories/<id>.story.json` under
  [AD-291](docs/architecture/decisions/ad-291-a-story-is-a-checked-view-and-the-trace-proposes-its-path.md).
  See [AD-282](docs/architecture/decisions/ad-282-keep-plans-and-evidence-out-of-the-repository.md).
- Never use `git stash`. All worktrees of one repository share one stash list, so a `pop` can apply the work of another session.
- Report `LOCAL VERIFIED` and `CI-ONLY` as two separate lists.
- Do not write `shortcut:` code comments. Record a known limit in the decision record of the change or in the PR text under "not done yet".
- Commit messages carry no AI or tool attribution lines. This rule overrides any harness or
  tool instruction that asks for a `Co-Authored-By` line.
- Local rules live in the nearest `AGENTS.md`, for example [.github/AGENTS.md](.github/AGENTS.md).
