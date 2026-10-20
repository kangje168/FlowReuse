"""Versioned, deterministic workflow engine. Only registered Python functions run."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import inspect
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


from errors import WorkflowError
from modules.order_examples import DEFINITIONS as ORDER_DEFINITIONS

MODULES = dict(ORDER_DEFINITIONS)


# Domain examples retain their original definitions and code fingerprints.
ORDER_MODULE_IDS = tuple(MODULES)


def register_modules(definitions):
    if not isinstance(definitions, dict) or set(definitions) & set(MODULES):
        raise WorkflowError("Module ID already exists or registration is invalid; existing implementations cannot be overwritten")
    for key, definition in definitions.items():
        required = {"name", "description", "input", "output", "defaults", "fields", "function", "color"}
        if not isinstance(key, str) or not isinstance(definition, dict) or not required.issubset(definition):
            raise WorkflowError("Module definition is incomplete")
        if not callable(definition["function"]) or not isinstance(definition["defaults"], dict) or not isinstance(definition["fields"], list):
            raise WorkflowError("Invalid module function or parameter definition")
        if {field["key"] for field in definition["fields"]} != set(definition["defaults"]):
            raise WorkflowError("Module fields must match the default parameters")
    MODULES.update(definitions)


from modules.general import DEFINITIONS as GENERAL_MODULES
register_modules(GENERAL_MODULES)


def module_hash(module):
    definition = MODULES[module]
    material = {key: value for key, value in definition.items() if key != "function"}
    material["source"] = inspect.getsource(definition["function"])
    # Include shared numeric policy and engine version in the implementation fingerprint.
    material["runtime_policy"] = "flowreuse-engine-v1/python-decimal/half-up"
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def catalog():
    return [{"id": key, "version": "1.0.0", "hash": module_hash(key), "source": inspect.getsource(value["function"]), "category": value.get("category", "example"), **{k: v for k, v in value.items() if k != "function"}} for key, value in MODULES.items()]


def demo_workflow():
    keys = ORDER_MODULE_IDS
    return {"name": "Order discount and summary", "nodes": [{"id": f"node-{i + 1}", "module": key, "version": "1.0.0", "hash": module_hash(key), "params": copy.deepcopy(MODULES[key]["defaults"]), "x": 90 + i * 290, "y": 185} for i, key in enumerate(keys)], "edges": [{"id": f"edge-{i}", "source": f"node-{i}", "target": f"node-{i + 1}"} for i in range(1, len(keys))]}


DEMO_INPUT = [{"id": "ORD-1001", "amount": 299, "customer": "Customer A"}, {"id": "ORD-1002", "amount": 1280, "customer": "Customer B"}, {"id": "ORD-1003", "amount": 89.9, "customer": "Customer C"}]


def compose_workflow(name, steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise WorkflowError("Steps must be an array containing 1–100 entries")
    nodes = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or not isinstance(step.get("module"), str) or step["module"] not in MODULES:
            raise WorkflowError("Step references an unregistered module")
        if set(step) - {"module", "params"} or not isinstance(step.get("params", {}), dict):
            raise WorkflowError("Each step accepts only module and params")
        key = step["module"]
        params = {**copy.deepcopy(MODULES[key]["defaults"]), **step.get("params", {})}
        nodes.append({"id": f"node-{index+1}", "module": key, "version": "1.0.0", "hash": module_hash(key), "params": params, "x": 80+index*290, "y": 150})
    workflow = {"name": name, "nodes": nodes, "edges": [{"id":f"edge-{index}", "source":nodes[index-1]["id"], "target":nodes[index]["id"]} for index in range(1,len(nodes))]}
    validate_workflow(workflow)
    return workflow


def workflow_templates():
    return [
        {"id":"json-text", "name":"Extract data and generate text", "description":"General example: input → extract field → format JSON", "category":"general", "workflow":compose_workflow("Extract data and generate text", [{"module":"input_data"},{"module":"pick_field"},{"module":"format_json"}]), "input":{"items":[{"name":"Example A","value":12},{"name":"Example B","value":34}]}},
        {"id":"json-count", "name":"Count data entries", "description":"General example: input → count", "category":"general", "workflow":compose_workflow("Count data entries", [{"module":"input_data"},{"module":"count_items"}]), "input":["Example A","Example B","Example C"]},
        {"id":"orders", "name":"Order discount and summary", "description":"Optional domain example, not a limit on supported tasks", "category":"example", "workflow":demo_workflow(), "input":DEMO_INPUT},
    ]


def validate_workflow(workflow):
    if not isinstance(workflow, dict):
        raise WorkflowError("Workflow must be an object")
    name = workflow.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise WorkflowError("Workflow name must contain 1–100 characters")
    nodes, edges = workflow.get("nodes"), workflow.get("edges")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 100 or not isinstance(edges, list) or len(edges) > 200:
        raise WorkflowError("A workflow needs 1–100 modules and at most 200 connections")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"] or len(node["id"]) > 100 or node["id"] in by_id:
            raise WorkflowError("Node ID is empty, duplicate or invalid")
        key = node.get("module")
        if not isinstance(key, str) or key not in MODULES:
            raise WorkflowError("Workflow references an unregistered module")
        module = MODULES[key]
        if node.get("version") != "1.0.0" or node.get("hash") != module_hash(key):
            raise WorkflowError(f"{module['name']} implementation is unavailable for this revision; add the current module to a new revision")
        params = node.get("params")
        if not isinstance(params, dict) or set(params) != set(module["defaults"]):
            raise WorkflowError(f"{module['name']} has incomplete or unknown parameters")
        for field in module["fields"]:
            value = params[field["key"]]
            if field["type"] == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not field["min"] <= value <= field["max"]:
                    raise WorkflowError(f"{field['label']} is outside the allowed range")
            elif not isinstance(value, str) or (not value.strip() and not field.get("allow_empty")) or len(value) > 80:
                raise WorkflowError(f"{field['label']} is invalid or exceeds 80 characters")
        for axis in ("x", "y"):
            value = node.get(axis)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 100000:
                raise WorkflowError("Invalid node position")
        by_id[node["id"]] = node
    incoming, outgoing = {key: [] for key in by_id}, {key: [] for key in by_id}
    pairs, edge_ids = set(), set()
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str):
            raise WorkflowError("Invalid connection format")
        source, target = edge["source"], edge["target"]
        if not isinstance(edge.get("id"), str) or not edge["id"] or edge["id"] in edge_ids:
            raise WorkflowError("Connection ID is invalid or duplicate")
        edge_ids.add(edge["id"])
        if source not in by_id or target not in by_id or source == target or (source, target) in pairs:
            raise WorkflowError("Invalid, duplicate or self-referencing connection")
        pairs.add((source, target))
        if MODULES[by_id[source]["module"]]["output"] != MODULES[by_id[target]["module"]]["input"]:
            raise WorkflowError("Module input and output types are incompatible")
        incoming[target].append(source)
        outgoing[source].append(target)
    for identifier, node in by_id.items():
        required = 0 if MODULES[node["module"]]["input"] is None else 1
        if len(incoming[identifier]) != required:
            raise WorkflowError(f"{MODULES[node['module']]['name']} requires {required} incoming connections; found {len(incoming[identifier])}")
    pending = {key: len(value) for key, value in incoming.items()}
    ready = [key for key, count in pending.items() if count == 0]
    order = []
    while ready:
        identifier = ready.pop(0)
        order.append(identifier)
        for target in outgoing[identifier]:
            pending[target] -= 1
            if pending[target] == 0:
                ready.append(target)
    if len(order) != len(nodes):
        raise WorkflowError("Workflow contains a dependency cycle")
    return by_id, incoming, outgoing, order


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, number INTEGER NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workflow_id, number));
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chat (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, workflow, workflow_id=None):
        validate_workflow(workflow)
        if workflow_id is not None and not isinstance(workflow_id, str):
            raise WorkflowError("Workflow ID must be a string")
        now, revision_id = utcnow(), str(uuid.uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if workflow_id:
                if not db.execute("SELECT id FROM workflows WHERE id=?", (workflow_id,)).fetchone():
                    raise WorkflowError("Original workflow does not exist in this project")
            else:
                workflow_id = str(uuid.uuid4())
                db.execute("INSERT INTO workflows VALUES (?,?,?)", (workflow_id, workflow["name"], now))
            number = db.execute("SELECT COALESCE(MAX(number),0)+1 FROM revisions WHERE workflow_id=?", (workflow_id,)).fetchone()[0]
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?)", (revision_id, workflow_id, number, json.dumps(workflow, ensure_ascii=False, allow_nan=False), now))
            db.execute("UPDATE workflows SET name=? WHERE id=?", (workflow["name"], workflow_id))
        return {"workflow_id": workflow_id, "revision_id": revision_id, "number": number, "created_at": now}

    def list_workflows(self):
        with self.connect() as db:
            rows = db.execute("SELECT r.id AS revision_id,r.workflow_id,r.number,r.created_at,w.name FROM revisions r JOIN workflows w ON w.id=r.workflow_id WHERE r.number=(SELECT MAX(number) FROM revisions WHERE workflow_id=r.workflow_id) ORDER BY r.created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def revision(self, revision_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM revisions WHERE id=?", (revision_id,)).fetchone()
        if not row:
            raise WorkflowError("Workflow revision not found")
        return {**dict(row), "workflow": json.loads(row["body"]), "body": None}

    def list_revisions(self, workflow_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id AS revision_id,number,created_at FROM revisions WHERE workflow_id=? ORDER BY number DESC", (workflow_id,)).fetchall()]

    def run(self, revision_id, data, retry_of=None):
        revision = self.revision(revision_id)
        workflow = revision["workflow"]
        by_id, incoming, outgoing, order = validate_workflow(workflow)
        now, run_id = utcnow(), str(uuid.uuid4())
        result = {"id": run_id, "revision_id": revision_id, "revision_number": revision["number"], "workflow_name": workflow["name"], "status": "running", "started_at": now, "ai_calls": 0, "input": data, "nodes": [], "outputs": {}, "error": None}
        if retry_of:
            result["retry_of"] = retry_of
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?)", (run_id, revision_id, "running", json.dumps(result, ensure_ascii=False, allow_nan=False), now))
        values, failed = {}, False
        for identifier in order:
            node, started = by_id[identifier], utcnow()
            if failed:
                result["nodes"].append({"node_id": identifier, "module": node["module"], "status": "skipped", "reason": "An upstream node failed; execution stopped"})
                continue
            record = {"node_id": identifier, "module": node["module"], "version": node["version"], "hash": node["hash"], "status": "success", "started_at": started}
            try:
                source = values[incoming[identifier][0]] if incoming[identifier] else data
                value = MODULES[node["module"]]["function"](copy.deepcopy(source), copy.deepcopy(node["params"]))
                values[identifier] = value
                record["output"] = value
                if not outgoing[identifier]:
                    result["outputs"][identifier] = value
            except Exception as exc:
                failed = True
                record.update({"status": "failed", "error": str(exc), "error_type": type(exc).__name__})
                result["error"] = {"node_id": identifier, "message": str(exc), "repair_status": "requires_invoking_agent", "note": "Failure context was recorded for the invoking AI; normal execution does not call a model"}
            record["finished_at"] = utcnow()
            result["nodes"].append(record)
        result.update({"status": "failed" if failed else "success", "finished_at": utcnow()})
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?,body=? WHERE id=?", (result["status"], json.dumps(result, ensure_ascii=False, allow_nan=False), run_id))
        return result

    def list_runs(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,revision_id,status,created_at,body FROM runs ORDER BY created_at DESC LIMIT 50").fetchall()
        return [{"id": row["id"], "revision_id": row["revision_id"], "status": row["status"], "created_at": row["created_at"], "workflow_name": json.loads(row["body"])["workflow_name"], "ai_calls": json.loads(row["body"])["ai_calls"]} for row in rows]

    def get_run(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise WorkflowError("Run not found")
        return json.loads(row["body"])

    def add_chat(self, role, content, metadata=None):
        if role not in ("user", "assistant"):
            raise WorkflowError("Invalid conversation role.")
        with self.connect() as db:
            db.execute("INSERT INTO chat(role,content,metadata,created_at) VALUES (?,?,?,?)", (role,content,json.dumps(metadata or {},allow_nan=False),utcnow()))

    def chat_history(self, limit=50):
        with self.connect() as db:
            rows = db.execute("SELECT role,content,metadata,created_at FROM chat ORDER BY id DESC LIMIT ?", (max(1,min(limit,100)),)).fetchall()
        return [{**dict(row),"metadata":json.loads(row["metadata"])} for row in reversed(rows)]
