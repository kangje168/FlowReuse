---
name: flowreuse-run
description: Reuse project-scoped FlowReuse workflows for repeated tasks. Execute a known revision with new input, obtain a refreshed project skill package, and investigate localized failure context only when required. Use the project copilot for first-time natural-language DAG construction, not for routine reruns.
---

# Project-scoped workflow reuse

Run `scripts/run_flowreuse.py` with Python. It locates the installation through `FLOWREUSE_HOME` or its enclosing repository checkout. Set `FLOWREUSE_HOME` when copying this skill to a personal skill directory and forwards arguments to its CLI. Always identify the intended project; use `projects` when it is unknown, then pass `--project <id>` before the subcommand. Do not use the standalone `--db` development mode for normal project work.

- Known revision: `--project <id> run --revision <revision> --input <file.json>`. Outputs stay in that project's output directory. Use the compact summary and file path without rereading code or all business rows.
- Discovery: `--project <id> discover --query <keywords>`. Read `modules --id <module>` only for a relevant contract; source requires `--source`.
- First construction: the UI copilot or `--project <id> chat --message <requirement> --language en|fr` uses that project's configured model to choose and connect a DAG. Add `--revision <id>` to refine it. This planning call costs model tokens; ordinary `run` does not.
- Direct composition: `compose --name <name> --steps-file <file.json>` accepts ordered `{module, params?}` entries and fills defaults, code references and typed connections. Missing capabilities require implementation, not fabricated success.
- Failure: exit 2 with `requires_ai: true` contains the failed node, parameters, error and upstream schema. Prefer `adapt --revision <id> --node <node> --params <JSON>` to append a fixed revision, or add `--fork-name <name>` for a separate variant. Never weaken business rules just to make invalid input pass.
- Retry: `retry --run <failed-run> --revision <fixed-revision>` reuses stored input without loading all rows into model context. Current modules are pure and the whole graph replays. Limit assistant-driven repair to two attempts, then report the blocker. External writes must not inherit this policy without idempotency and recovery.
- Every scoped invocation refreshes `.frskill.json` and a short English `SKILL.md`, including operational failures. Use the returned `skill_snapshot` paths and generation as current. Refreshing does not call a model or regenerate business code. `bundle` refreshes explicitly.
- Exit 1 means invocation/configuration/storage failure; correct that cause first. A nonexistent project cannot yield a valid package. Parser help does not select a project.

Project storage, conversation, credentials and outputs are separate, while built-ins are shared read-only. Skill manifests exclude keys, raw business input/output and transcripts. This is a local single-user tool, not an arbitrary-code sandbox or a new grant of external-action permissions. Engine `ai_calls: 0` excludes tokens spent by this assistant and the separate planning conversation.
