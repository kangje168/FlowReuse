"""Fresh, secret-free project skill snapshots, generated without a model."""
import hashlib
import json
import os
from pathlib import Path
import uuid

from engine import catalog, utcnow
from projects import atomic_json

ROOT = Path(__file__).resolve().parent


def refresh_bundle(store, project=None, command="refresh"):
    project = project or {"id":"standalone", "name":"Standalone database", "ai":{}}
    root = getattr(store, "project_root", store.path.parent)
    generation = uuid.uuid4().hex
    folder = root / "skill" / "versions" / generation
    folder.mkdir(parents=True, exist_ok=False)
    allowed = project.get("allowed_modules")
    modules = [{key:module[key] for key in ("id","name","description","version","hash","input","output","defaults","fields")} for module in catalog() if allowed is None or module["id"] in allowed]
    workflows = []
    for row in store.list_workflows():
        definition = store.revision(row["revision_id"])["workflow"]
        workflows.append({**row, "nodes":[{"id":n["id"],"module":n["module"],"version":n["version"],"hash":n["hash"],"parameter_names":list(n["params"])} for n in definition["nodes"]]})
    manifest = {"format":"flowreuse.skill", "format_version":"1.0", "generation":generation, "generated_at":utcnow(), "project":{"id":project["id"],"name":project["name"]}, "invocation":command, "ai":{"provider":project.get("ai",{}).get("provider"),"model":project.get("ai",{}).get("model")}, "execution":{"model_calls_on_success":0,"arbitrary_code_execution":False,"retry":"pure_registered_modules_only"}, "modules":modules,"workflows":workflows}
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode()
    (folder / "manifest.frskill.json").write_bytes(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    prefix = f'python "{ROOT / "cli.py"}" --project {project["id"]}'
    description = json.dumps("Execute saved workflows inside the isolated FlowReuse project " + project["name"] + ". Reuse known revisions and inspect only localized failure context.",ensure_ascii=False)
    document = f'''---
name: flowreuse-project-{project['id']}
description: {description}
---

# Project execution skill

Project: `{project['id']}`. Snapshot: `{generation}`.
Manifest SHA-256: `{digest}`. Read `manifest.frskill.json` only when discovery is needed.

- Known workflow: `{prefix} run --revision <id> --input <file.json>`.
- Discovery: `{prefix} discover --query <keywords>`.
- Success: use the compact summary and output file; do not reload source or business rows.
- Failure: inspect the returned node and schema. Prefer `adapt` for a parameter fix, then `retry` with the stored input. Limit automatic repair to two attempts.
- New requirements: use the project's AI chat or `compose` with existing module contracts. Unsupported capabilities require implementation, not fabricated results.
- Every CLI invocation refreshes this project's skill snapshot without a model call. Use the returned `skill_snapshot` paths as the current authoritative generation.
- Project isolation covers storage and configuration, not separate operating-system users or an arbitrary-code sandbox. No credentials or business inputs are included here.
'''
    (folder / "SKILL.md").write_text(document, encoding="utf-8")
    pointer = {"format":"flowreuse.skill.pointer", "project_id":project["id"], "generation":generation, "generated_at":manifest["generated_at"], "manifest_sha256":digest, "manifest":str(folder / "manifest.frskill.json"), "skill":str(folder / "SKILL.md")}
    atomic_json(root / "skill" / "latest.json", pointer)
    # Convenience mirror; latest.json always points to the coherent immutable pair.
    mirror = root / "skill" / ("SKILL." + generation + ".tmp")
    mirror.write_text(document, encoding="utf-8")
    os.replace(mirror, root / "skill" / "SKILL.md")
    return pointer
