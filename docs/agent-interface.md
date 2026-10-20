# Agent interface

Identify the intended project and keep passing `--project <id>`. Do not search another project's runs or reuse a revision across projects merely because its name looks similar. Use `projects` for metadata discovery when the project is unknown.

## Cheap repeat execution

Run a known frozen revision directly:

```text
python cli.py --project <id> run --revision <revision> --input <input.json>
```

The engine writes outputs inside the project and returns compact JSON, including the run ID, summary, output file and fresh `skill_snapshot`. It does not regenerate code, interpret the requirement again, or call the model. Do not read the complete business output or Python source into context unless the user's result requires it.

`ai_calls: 0` counts engine model calls. It excludes assistant reasoning and the separate copilot planning conversation.

## Discovery and initial construction

- `discover --query <keywords>` searches saved names and returns latest revision references.
- `modules` returns general contracts without source; `--id <module>` narrows the request and `--source` explicitly includes code.
- `compose --name <name> --steps-file <file.json>` builds a validated linear chain from short `{module, params?}` entries. The tool fills code references and connections.
- `chat --message <requirement> --language en|fr` calls the project's configured model to choose and connect a DAG. Add `--revision <id>` to refine a saved workflow. This is a model call; repeat execution should use `run` instead.
- `describe --revision <id>` returns a definition when a structural edit is necessary. `save --file <workflow.json> --workflow <workflow-id>` appends a revision.

The copilot cannot create new executable capabilities by naming nonexistent modules. Missing capabilities need implementation and verification first. It never executes arbitrary response text.

## Failure handling

Exit code 2 and `requires_ai: true` return the failed node, parameters, error and upstream field types without automatically returning business rows. Inspect the affected contract only. Prefer `adapt --revision <id> --node <node-id> --params <JSON>` for a local parameter fix; add `--fork-name <name>` for an independent variant. Do not weaken business validation to make corrupt data pass.

Use `retry --run <failed-run> --revision <fixed-revision>` to reuse stored input without reloading all rows into model context. Current modules are pure, so this replays the entire graph. Limit assistant-driven repair to two attempts and report the blocker afterward. This is a skill convention, not a server-wide restriction on manual CLI use. Checkpoint resume and external-effect recovery are not implemented.

Exit code 1 indicates invocation, configuration or storage failure. Correct the cause before treating it as a node-code problem.

## Skill refresh

Every scoped CLI result refreshes the current project's package, including operational failures. The response's `skill_snapshot` points to a generation-specific manifest and English instructions. A nonexistent project cannot produce a valid project skill. The `--help` parser does not select a project and does not create a snapshot.

`bundle` refreshes explicitly. `export --run <id> --output <project-output.json>` retrieves complete results locally. Project mode rejects output paths outside its `outputs/`. `--db` is an explicit standalone development/test escape hatch and is not the multi-project agent interface.
