# FlowReuse

An AI-first workflow workspace: describe a task, let the project's AI build and connect the DAG, then reuse a frozen executable revision. Routine execution uses no model. External assistants receive compact results and localized failure context.

Version 0.3 is a local, single-user application. Application code and documentation are maintained in English. The interface switches between English and French.

## Start

Python 3.10+ is required; no third-party packages are needed. Python 3.12 has been verified.

Double-click `start.cmd`, or run:

```powershell
python server.py --open
```

Open [the local application](http://127.0.0.1:8765). The service binds only to loopback. Stop it with Ctrl+C in its terminal.

## Intended interaction

1. Create or select a project. Workflows, revisions, runs, conversations, output files, AI settings and skill snapshots belong to that project.
2. Open **Project AI**. Choose an OpenAI-compatible endpoint or local Ollama, and enter an available model ID. For a remote endpoint, enter its API key in the settings form, not in chat.
3. Describe the input, rules and expected output in the compact copilot panel. The selected model chooses modules, parameters and connections; a validated DAG appears on the canvas and is saved as a new revision. Ambiguous requests should produce a clarification. Unsupported capabilities must be reported rather than invented.
4. Review the graph, enter business input in **Input**, and run it. Building a graph never runs it automatically.
5. Reuse the saved revision through the project skill. Successful code-only repeats execute without a model. The invoking assistant handles failures using compact context and bounded repairs.

There is no fake AI fallback. If no model is configured, the application asks for configuration. Provider transport and DAG creation have been tested against local protocol fixtures, not a paid live model account. Live generation quality remains to be evaluated with the user's selected model.

## Project isolation

Projects live under `data/projects/<project-id>/`:

```text
project.json                   Project metadata and AI profile, without a plaintext key
credential.bin                 Optional Windows-DPAPI-protected project key
workflows.sqlite3              This project's workflows, runs and conversation
outputs/                       This project's CLI outputs
skill/latest.json              Pointer to the current coherent skill generation
skill/SKILL.md                 Convenience mirror of the latest instructions
skill/versions/<generation>/   Immutable SKILL.md + manifest.frskill.json pair
```

API access resolves workflow and run IDs only inside the selected project's database. The built-in module library is shared read-only; mutable state is not shared. Output paths from project CLI execution are restricted to that project's `outputs/` directory.

This is application-level separation for one local OS user, not multi-tenant authorization or a separate OS sandbox. A local administrator still controls all project files. Arbitrary generated Python code is not executed.

The old `data/flowreuse.sqlite3` is copied into the default project on first migration and is left intact. If the English source migration changes module fingerprints, a new compatible workflow revision is appended; historical definitions are not overwritten. Historical executable code archives are not yet implemented.

## AI configuration

- **OpenAI-compatible**: a Chat Completions base URL, for example `https://api.openai.com/v1`, plus a model ID and key. The endpoint must support JSON responses. The adapter uses the documented [Chat Completions API](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create).
- **Ollama**: a local base URL such as `http://127.0.0.1:11434` and an installed model name. The adapter uses [Ollama chat](https://docs.ollama.com/api/chat) with JSON format.

Remote endpoints require HTTPS. HTTP is allowed only on loopback. Redirects are refused so credentials are not forwarded to a different destination. Stored keys are protected with Windows DPAPI and project-specific entropy; changing the provider or endpoint does not implicitly reuse a saved key. An explicitly configured project environment-variable reference is also supported through the CLI.

The copilot sends the typed conversation and registered module/graph structure when **Send** is pressed. It does not automatically attach execution input rows, complete run outputs or API keys to model messages. Conversation history is project-scoped. `ai_calls` on an engine run excludes the separate planning conversation and does not mean that the invoking assistant consumes no tokens.

## Reusable skill packages

Every project-scoped CLI invocation, including an operational failure, generates a fresh skill snapshot without a model call. The response includes `project_id` and `skill_snapshot` paths. Invalid project IDs cannot produce a package for a nonexistent project.

The versioned **FlowReuse Skill Manifest 1.0** uses ordinary JSON with a `.frskill.json` extension. It contains project identity, supported module contracts, code fingerprints and latest workflow revision references. It excludes keys, conversations, source bodies and business input/output rows. A short English `SKILL.md` provides the external assistant's execution instructions. `skill/latest.json` atomically points to a coherent immutable pair, while the schema is maintained in `schemas/frskill.schema.json`.

Use **Export skill** to download a ZIP containing the manifest, its schema and the matching `SKILL.md`. Package refresh is deterministic; it does not regenerate business code on every call.

## CLI

The CLI works without starting the web server. Prefer explicit project IDs:

```powershell
python cli.py projects
python cli.py project-create --name "Research tasks"
python cli.py --project <id> project-config --provider ollama --base-url http://127.0.0.1:11434 --model <installed-model>
python cli.py --project <id> chat --message "Extract items and format them as text"
python cli.py --project <id> discover --query "extract"
python cli.py --project <id> run --revision <revision-id> --input examples/data.json
python cli.py --project <id> bundle
```

Successful output files are written automatically into the selected project. Return codes are 0 for success, 2 for a node execution failure and 1 for invocation/configuration failure. The personal `flowreuse-run` skill forwards these operations and is maintained from `.agents/skills/flowreuse-run/`.

Read [the agent interface](docs/agent-interface.md), [architecture](docs/architecture.md), [module extension guide](docs/module-extension.md), [roadmap](docs/roadmap.md), [skill format](docs/skill-format.md), or [related products](docs/related-products.md) as needed.

## Verification and limits

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
node --check web/i18n.js
```

Tests cover deterministic reruns, immutable revisions, cross-project API/store access rejection, output boundaries, protected keys, fresh skill generations, structured model transport, typed DAG validation, and no model calls during normal execution. API/model protocol tests listen on temporary loopback ports and use temporary databases under `work/tests/`.

The initial general registry contains JSON input/extraction/formatting, text replacement/splitting, and counting. Order processing is an optional domain example. This does not yet implement arbitrary generated-code isolation, native Anthropic protocol, external side-effect recovery, multi-input joins, scheduling or multi-user access control. The copilot cannot invent these capabilities. Failed pure workflows are replayed in full; checkpoint recovery is not implemented.

Keep your checkout outside cloud-synchronized folders if you do not want local project data backed up by those services. Runtime data, credentials, generated outputs and skill snapshots are excluded from version control.
