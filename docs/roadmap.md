# Roadmap

## Implemented in 0.3

- Conversation-first DAG construction through a per-project selected model.
- OpenAI-compatible and Ollama protocols; structured responses validated before saving.
- Project-separated databases, runs, conversations, model profiles, encrypted credentials and outputs.
- English/French UI and English source/documentation.
- Versioned JSON skill manifests plus English SKILL.md, refreshed without a model on each scoped CLI result.
- Canvas editing, typed acyclic graph validation, immutable revisions, deterministic execution and compact failure handoff.

## Next practical validation

Configure a real project model and evaluate generation quality against a real repeated task. Extend the module registry for that task rather than pretending that general JSON/text modules cover every use case. Measure model calls, input/output context and token use separately; do not substitute a fixed savings percentage for measurement.

## Remaining engineering

- Isolated execution and verification of newly generated code; archived executable module versions.
- Checkpoint recovery, idempotency and confirmed outcomes for external effects.
- Multi-input joins, schedules, cancellation and asynchronous execution events.
- Broader provider protocols and model-capability negotiation.
- File/document/API module packs, project export/import and package retention management.
- Multi-user authorization if the product moves beyond a local single-user installation.

No external-effect module should inherit the pure-transform retry policy without recovery support.
