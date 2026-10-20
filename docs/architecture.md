# Architecture

## Conversation before canvas

The customer's first interaction is a natural-language conversation. The selected project model returns a structured explanation and optional plan. The server materializes registered module references, pins current code fingerprints, validates parameters/types/acyclicity, lays out nodes, and saves a revision. The customer reviews the resulting DAG. Manual dragging is an editing capability, not a prerequisite for initial construction.

The model may ask for clarification or report missing capabilities instead of producing a plan. Neither model output nor chat text is evaluated as code. Generated plans never trigger execution automatically.

## Projects

`ProjectManager` resolves validated project IDs to independent folders. Each project has a separate SQLite database for workflow revisions, runs and conversations; AI configuration, encrypted key, output directory and generated skills are also separate. The application has no global mutable conversation or global selected model. Browser requests carry `X-FlowReuse-Project`, and lookups never fall back to another database.

The module registry is a shared, explicitly registered library of stateless functions. Module parameters and runtime data are copied before execution. Project isolation here does not create separate OS accounts or protect files from the local owner.

## AI boundary

`ai.py` implements OpenAI-compatible Chat Completions and Ollama chat transport. The project selects protocol, endpoint, model and credential. Keys are encrypted with Windows DPAPI and bound to project and destination. Remote transport uses HTTPS, refuses redirects, limits response size and uses a timeout. Provider error bodies and keys are not echoed to the browser.

Planning receives module contracts, the current graph and a bounded project conversation. Business execution inputs and full logs are not automatically included. The model is called only for an explicit copilot request; successful deterministic execution has no model client.

## Execution and revisions

A revision freezes module IDs, implementation fingerprints, node parameters, positions and edges. The engine validates references, matching port types, single-input constraints and acyclicity before saving or running. Topological execution is independent of canvas position and supports fan-out. Joins and distributed execution are not implemented.

The engine records inputs, per-node outputs/status/timestamps and final results in the project's database. A failed node stops the run; remaining nodes are marked skipped. Registered modules currently have no external effects, so retry replays the entire graph. External writes require a separate idempotency and recovery design before automatic retries are enabled.

Code fingerprints include registered metadata and function source. Replacing code does not silently modify an existing revision. Executable multi-version code archives remain future work. The English migration preserves original legacy data and appends new compatible revisions rather than editing old definitions.

## Skill lifecycle

`skill_bundle.py` creates a model-free snapshot after every scoped CLI result and relevant UI save/run/chat/configuration operation. An immutable generation contains the English instructions and JSON manifest. An atomic pointer identifies a coherent pair. The manifest references revisions and capabilities; it does not include credentials or business rows. The external assistant can invoke a known revision directly and inspect only failure context when necessary.

## Interface language

Application source text is English. `web/i18n.js` contains the French presentation dictionary. The locale switch updates labels, module presentation, accessibility labels and copilot reply language. Workflow IDs, stored user content, code and schema keys do not change when the UI language changes. Provider diagnostics and code remain in English.
