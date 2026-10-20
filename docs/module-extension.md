# Extending capabilities

The engine is domain-neutral. General JSON/text modules live in `modules/general.py`; order processing lives in `modules/order_examples.py` as an optional example. Registered functions and contracts determine executable capabilities, not a hard-coded business domain.

A module exposes `function(data, params)` and returns a JSON-serializable result. Its definition includes a stable ID, English name/description, input/output type names, default parameters, form fields, callable and presentation metadata. Explicitly register reviewed definitions with `register_modules`; duplicate IDs are rejected.

Port compatibility is necessary but not sufficient: the function must validate real input and preserve business semantics. Current parameter forms support text and number fields. New parameter structures require server-side validation and interface support.

Module hashes include source and metadata. Do not overwrite old fingerprints or edit historical workflow definitions to hide implementation changes. Full executable module-version archives and arbitrary generated-code isolation are not implemented.

Files, APIs, document generation and other domains can be added through modules, but are not automatically available today. External writes must first define idempotency, outcome confirmation and recovery. Current full-graph retries are valid only for the pure built-in transformations.
