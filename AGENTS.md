# Product intent and implementation boundaries

The user wants a generic AI-first workflow reuse tool. The customer initially describes a task to the embedded project copilot, which chooses modules and creates the connected DAG. Routine external AI skill calls should execute a known revision, receive compact results, and involve the model only when needed. Order workflows are optional examples, not the product domain.

Keep source and documentation in English. Maintain English/French interface switching. Presentation language must never change IDs, code hashes, data ownership or schema keys.

Preserve project isolation: each project owns its database, conversation, AI profile, credential, output directory and generated skills. Shared built-ins are read-only stateless functions. This is local single-user separation, not multi-tenant authorization or an OS sandbox. Never resolve a workflow/run ID in another database as a fallback.

Every scoped CLI result must refresh the project's model-free skill snapshot. Keep generation files coherent through the atomic latest pointer. Do not include API keys, business rows, source bodies or chat transcripts in generated manifests. Do not claim zero assistant tokens when only engine calls are zero.

The copilot supports OpenAI-compatible and Ollama APIs. It may create validated graphs only from registered capabilities; it must clarify or report missing capabilities rather than invent code. Building a plan must not execute it. Arbitrary generated-code execution and archived executable module versions remain future work. Current retries replay pure transformations; external writes require separate idempotency and recovery support.

Use project-specific, destination-bound credentials. Never echo provider response bodies containing unknown sensitive content. Do not send full business input to planning by default. No test may call a paid/live model without actual authorization and configuration; protocol fixtures must be labeled as fixtures.

Start with `python server.py`; `start.cmd` opens the browser. Verify with `python -m unittest discover -s tests -v`, `node --check web/app.js`, and `node --check web/i18n.js`. Temporary databases belong in work/tests; API/model protocol tests require loopback access.

Personal skill source: `.agents/skills/flowreuse-run/`. Optional installed copy: `$CODEX_HOME/skills/flowreuse-run`. Set `FLOWREUSE_HOME` to the checkout path when using an installed copy. Keep intentional updates synchronized without replacing unrelated skills.
