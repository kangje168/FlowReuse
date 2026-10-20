"""Compact machine interface for agents; no web server or model required."""
import argparse
import json
import os
import sys
from pathlib import Path

from engine import Store, WorkflowError, MODULES, catalog, workflow_templates, compose_workflow, validate_workflow

ROOT = Path(__file__).resolve().parent
_invocation = None


def read_json(path):
    def reject(value):
        raise ValueError("Non-finite numbers are not allowed in JSON")
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=reject)


def emit(value):
    if _invocation is not None:
        from skill_bundle import refresh_bundle
        store, project, command = _invocation
        value = {**value,"project_id":project["id"],"skill_snapshot":refresh_bundle(store,project,command)}
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


def schema_of(value):
    if isinstance(value, list):
        return {"type": "array", "count": len(value), "item": schema_of(value[0]) if value else None}
    if isinstance(value, dict):
        return {"type": "object", "fields": {key: type(item).__name__ for key, item in value.items()}}
    return {"type": type(value).__name__}


def failure_context(store, run):
    if run["status"] != "failed":
        return {"run_id": run["id"], "requires_ai": False, "status": run["status"]}
    revision = store.revision(run["revision_id"])
    workflow = revision["workflow"]
    failed = next(node for node in run["nodes"] if node["status"] == "failed")
    node = next(node for node in workflow["nodes"] if node["id"] == failed["node_id"])
    upstream_ids = [edge["source"] for edge in workflow["edges"] if edge["target"] == node["id"]]
    upstream = next((item["output"] for item in run["nodes"] if item["node_id"] in upstream_ids and item["status"] == "success"), run["input"])
    return {"run_id": run["id"], "requires_ai": True, "workflow_id": revision["workflow_id"], "revision_id": run["revision_id"], "node_id": node["id"], "module": node["module"], "params": node["params"], "error": failed["error"], "error_type": failed["error_type"], "upstream_schema": schema_of(upstream), "side_effects": "none_registered_modules_only", "next": "Inspect this node only; prefer a parameter fix. Save a new revision, then rerun. Do not change business rules to hide invalid data."}


def compact_result(store, run, output_path=None):
    value = {"run_id": run["id"], "status": run["status"], "revision_id": run["revision_id"], "ai_calls": run["ai_calls"], "requires_ai": run["status"] == "failed"}
    if run["status"] == "failed":
        value["failure"] = failure_context(store, run)
    else:
        reports = []
        for node_id, output in run["outputs"].items():
            if isinstance(output, dict) and all(key in output for key in ("count", "currency", "gross", "discount", "net")):
                reports.append({"node_id": node_id, **{key: output[key] for key in ("count", "currency", "gross", "discount", "net")}})
            else:
                reports.append({"node_id": node_id, "schema": schema_of(output)})
        value["summary"] = reports
        value["output_file"] = str(output_path) if output_path else None
        if not output_path:
            value["retrieve"] = f"python cli.py export --run {run['id']} --output <file.json>"
    return value


def export_output(store, run, path):
    target = Path(path).resolve()
    project_root = getattr(store,"project_root",None)
    if project_root and not target.is_relative_to(project_root / "outputs"):
        raise WorkflowError("Project outputs must stay inside this project's outputs directory.")
    if target == store.path.resolve() or target.suffix.lower() != ".json":
        raise WorkflowError("Output must be a .json file and cannot overwrite the database")
    if not project_root and target.is_relative_to(ROOT) and not target.is_relative_to(ROOT / "outputs") and not target.is_relative_to(ROOT / "work"):
        raise WorkflowError("Write generated artifacts into outputs/ or work/ to avoid overwriting source files")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp-" + run["id"])
    temporary.write_text(json.dumps(run["outputs"], ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return target


def make_parser():
    parser = argparse.ArgumentParser(description="FlowReuse agent interface: JSON summaries by default")
    parser.add_argument("--db",help="Explicit standalone development database; not the project interface")
    parser.add_argument("--project",default="default",help="Isolated project ID")
    parser.add_argument("--projects-root",default=str(ROOT/"data"/"projects"),help="Project storage root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("projects",help="List project metadata without their workflows or secrets")
    create = commands.add_parser("project-create")
    create.add_argument("--name",required=True)
    configure = commands.add_parser("project-config")
    configure.add_argument("--provider",choices=["compatible","ollama"])
    configure.add_argument("--model")
    configure.add_argument("--base-url")
    configure.add_argument("--key-env")
    commands.add_parser("bundle",help="Generate a fresh .frskill.json and SKILL.md without a model")
    conversation = commands.add_parser("chat",help="Ask the project's selected AI to build or refine a DAG")
    conversation.add_argument("--message",required=True)
    conversation.add_argument("--language",choices=["en","fr"],default="en")
    conversation.add_argument("--revision",help="Refine an existing revision in this project")
    discover = commands.add_parser("discover", help="Find reusable saved workflows without loading code")
    discover.add_argument("--query", default="")
    modules = commands.add_parser("modules", help="Read module contracts; source is opt-in")
    modules.add_argument("--id")
    modules.add_argument("--source", action="store_true")
    modules.add_argument("--category", choices=["general","example","all"], default="general")
    demo = commands.add_parser("seed-demo", help="Save an optional sample flow once and return its IDs")
    demo.add_argument("--template", choices=["json-text","json-count","orders"], default="json-text")
    compose = commands.add_parser("compose", help="Create a connected chain from short module steps; code hashes and defaults are automatic")
    compose.add_argument("--name", required=True)
    steps = compose.add_mutually_exclusive_group(required=True)
    steps.add_argument("--steps", help="JSON array of {module, params?}")
    steps.add_argument("--steps-file", help="Path to the JSON step array")
    describe = commands.add_parser("describe", help="Read one workflow revision only")
    describe.add_argument("--revision", required=True)
    save = commands.add_parser("save", help="Validate a workflow JSON and create an immutable revision")
    save.add_argument("--file", required=True)
    save.add_argument("--workflow", help="Append a revision to an existing workflow")
    validate = commands.add_parser("validate")
    validate.add_argument("--file", required=True)
    adapt = commands.add_parser("adapt", help="Change one node's parameters without reading or rewriting the entire workflow")
    adapt.add_argument("--revision", required=True)
    adapt.add_argument("--node", required=True)
    adapt.add_argument("--params", required=True, help="JSON object of parameter overrides")
    adapt.add_argument("--fork-name", help="Create a separate workflow rather than append a revision")
    run = commands.add_parser("run", help="Run a frozen revision; normal execution uses zero model calls")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--revision")
    source.add_argument("--workflow", help="Resolve latest once, then execute its frozen revision")
    run.add_argument("--input", required=True)
    run.add_argument("--output")
    retry = commands.add_parser("retry", help="Run a repaired revision with a previous run's stored input")
    retry.add_argument("--run", required=True)
    retry.add_argument("--revision", required=True)
    retry.add_argument("--output")
    commands.add_parser("runs", help="Recent run metadata without business data")
    failure = commands.add_parser("failure", help="Failure and input schema, not full data or code")
    failure.add_argument("--run", required=True)
    export = commands.add_parser("export", help="Write output locally without putting it into model context")
    export.add_argument("--run", required=True)
    export.add_argument("--output", required=True)
    return parser


def main(argv=None):
    global _invocation
    _invocation = None
    args = make_parser().parse_args(argv)
    try:
        manager = None
        if args.db:
            store = Store(args.db)
            project = {"id":"standalone","name":"Standalone development database","ai":{}}
        else:
            from projects import ProjectManager
            manager = ProjectManager(args.projects_root,legacy_database=ROOT/"data"/"flowreuse.sqlite3")
            project = manager.create(args.name) if args.command=="project-create" else manager.public(args.project)
            store = manager.store(project["id"])
        _invocation = (store,project,args.command)
        if args.command == "projects":
            if not manager:
                raise WorkflowError("Project commands cannot use --db.")
            emit({"projects":manager.list()})
        elif args.command == "project-create":
            emit({"project":project})
        elif args.command == "project-config":
            if not manager:
                raise WorkflowError("Project commands cannot use --db.")
            settings = {key:getattr(args,key) for key in ("provider","model","base_url","key_env") if getattr(args,key) is not None}
            project = manager.configure(project["id"],settings)
            _invocation = (store,project,args.command)
            emit({"project":project})
        elif args.command == "bundle":
            emit({"status":"refreshed"})
        elif args.command == "chat":
            if not manager:
                raise WorkflowError("AI chat needs an isolated project, not --db.")
            from ai import chat
            body = {"message":args.message}
            if args.revision:
                revision = store.revision(args.revision)
                body.update(workflow=revision["workflow"],workflow_id=revision["workflow_id"])
            emit(chat(manager,project["id"],body,args.language))
        elif args.command == "discover":
            items = store.list_workflows()
            query = args.query.casefold()
            emit({"workflows": [item for item in items if query in item["name"].casefold()], "ai_calls": 0})
        elif args.command == "modules":
            if args.id and args.id not in MODULES:
                raise WorkflowError("Module not found")
            items = []
            for item in catalog():
                if args.id and item["id"] != args.id:
                    continue
                if not args.id and args.category != "all" and item["category"] != args.category:
                    continue
                if not args.source:
                    item.pop("source")
                items.append(item)
            emit({"modules": items})
        elif args.command == "seed-demo":
            template = next(item for item in workflow_templates() if item["id"] == args.template)
            existing = next((item for item in store.list_workflows() if item["name"] == template["name"]), None)
            emit(existing or store.save(template["workflow"]))
        elif args.command == "compose":
            steps = read_json(args.steps_file) if args.steps_file else json.loads(args.steps)
            emit(store.save(compose_workflow(args.name, steps)))
        elif args.command == "describe":
            revision = store.revision(args.revision)
            emit({"revision_id": revision["id"], "workflow_id": revision["workflow_id"], "number": revision["number"], "workflow": revision["workflow"]})
        elif args.command == "save":
            emit(store.save(read_json(args.file), args.workflow))
        elif args.command == "validate":
            _, _, _, order = validate_workflow(read_json(args.file))
            emit({"valid": True, "order": order})
        elif args.command == "adapt":
            revision = store.revision(args.revision)
            workflow = revision["workflow"]
            node = next((item for item in workflow["nodes"] if item["id"] == args.node), None)
            if not node:
                raise WorkflowError("Node to adapt was not found")
            patch = json.loads(args.params)
            if not isinstance(patch, dict):
                raise WorkflowError("Parameter overrides must be a JSON object")
            node["params"].update(patch)
            workflow["derived_from"] = {"revision_id": args.revision, "node_id": args.node}
            if args.fork_name:
                workflow["name"] = args.fork_name
            emit(store.save(workflow, None if args.fork_name else revision["workflow_id"]))
        elif args.command == "run":
            revision_id = args.revision
            if args.workflow:
                match = next((item for item in store.list_workflows() if item["workflow_id"] == args.workflow), None)
                if not match:
                    raise WorkflowError("Workflow not found in this project")
                revision_id = match["revision_id"]
            if args.output and Path(args.input).resolve() == Path(args.output).resolve():
                raise WorkflowError("Output cannot overwrite this run’s input")
            run = store.run(revision_id, read_json(args.input))
            destination = args.output or (str(store.project_root/"outputs"/(run["id"]+".json")) if hasattr(store,"project_root") else None)
            output = export_output(store, run, destination) if destination and run["status"] == "success" else None
            emit(compact_result(store, run, output))
            return 2 if run["status"] == "failed" else 0
        elif args.command == "retry":
            previous = store.get_run(args.run)
            run = store.run(args.revision, previous["input"], retry_of=previous["id"])
            destination = args.output or (str(store.project_root/"outputs"/(run["id"]+".json")) if hasattr(store,"project_root") else None)
            output = export_output(store, run, destination) if destination and run["status"] == "success" else None
            emit(compact_result(store, run, output))
            return 2 if run["status"] == "failed" else 0
        elif args.command == "runs":
            emit({"runs": store.list_runs()})
        elif args.command == "failure":
            emit(failure_context(store, store.get_run(args.run)))
        elif args.command == "export":
            run = store.get_run(args.run)
            if run["status"] != "success":
                raise WorkflowError("Only successful run outputs can be exported")
            emit({"run_id": args.run, "output_file": str(export_output(store, run, args.output))})
        return 0
    except (WorkflowError, OSError, ValueError, TypeError) as exc:
        emit({"status": "error", "error": str(exc), "requires_ai": True})
        return 1
    finally:
        _invocation = None


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
