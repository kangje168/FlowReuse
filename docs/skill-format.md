# FlowReuse Skill Manifest 1.0

The `.frskill.json` extension identifies a versioned JSON contract; it is not a new programming language. Any JSON parser can read it. The JSON Schema is in `schemas/frskill.schema.json`.

## Contents

- Format/version, generation UUID and UTC generation time.
- Project ID/name and the operation that produced the snapshot.
- Selected AI provider protocol and model name, without its key or endpoint secrets.
- Execution policy: ordinary repeats use no model; arbitrary code is not executed; current retries are for pure registered transformations.
- Registered module contracts, default parameters, implementation versions and source fingerprints.
- Saved workflows' latest revision references and node module/fingerprint/parameter-name metadata.

Business input/output rows, conversations, credential values and source bodies are intentionally omitted. Module defaults are application-defined constants; workflow runtime parameter values are not exported in the manifest.

## Coherent generations

`skill/versions/<generation>/` contains `manifest.frskill.json` and `SKILL.md`. Once written, a generation is not modified. `latest.json` is atomically replaced to point to the current pair and includes the manifest SHA-256. `skill/SKILL.md` is only a convenience mirror; use the pointer for coherent reads. Generations are refreshed on each scoped CLI result and relevant application mutation. Refreshing never calls a model.

The interface's ZIP export includes the matching manifest, instructions and schema. A generated skill describes how to invoke the local installation; exporting it does not move the project's database or grant a remote AI access to local files. A receiving assistant needs an authorized execution bridge to the same installation.

## Evolution

Future incompatible contracts must increment the format version. Consumers should reject unknown major versions rather than guessing. No claim is made that this manifest is compatible with Dify DSL, Windmill OpenFlow, Airflow DAG files or another vendor's skill format. Standard JSON and a conventional SKILL.md keep a simple integration path while the contract evolves.
