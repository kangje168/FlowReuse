"""Project-scoped storage and AI profiles for the local single-user application."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid

from engine import Store, MODULES, module_hash, utcnow
from errors import WorkflowError


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def protect_secret(data, project_id, decrypt=False):
    if os.name != "nt":
        raise WorkflowError("Persistent API keys require Windows DPAPI on this installation. Use a project environment variable instead.")
    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    def blob(value):
        buffer = ctypes.create_string_buffer(value)
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer
    source, source_buffer = blob(data)
    entropy, entropy_buffer = blob(project_id.encode())
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob),ctypes.c_wchar_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype = wintypes.BOOL
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), "FlowReuse project key", ctypes.byref(entropy), None, None, 1, ctypes.byref(target))
    if not ok:
        raise WorkflowError("Windows could not protect or unlock this project's API key.")
    try:
        return ctypes.string_at(target.data, target.length)
    finally:
        kernel = ctypes.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class ProjectManager:
    def __init__(self, root, legacy_database=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.chat_locks = {}
        if not (self.root / "default" / "project.json").exists():
            project = self.create("Personal workspace", identifier="default")
            if legacy_database and Path(legacy_database).is_file():
                # Copy, never move or rewrite the original pre-project database.
                store_path = self.path(project["id"]) / "workflows.sqlite3"
                shutil.copy2(legacy_database, store_path)
                store = self.store(project["id"])
                for row in store.list_workflows():
                    workflow = store.revision(row["revision_id"])["workflow"]
                    changed = False
                    for node in workflow["nodes"]:
                        if node["module"] in MODULES and node["hash"] != module_hash(node["module"]):
                            node["hash"] = module_hash(node["module"])
                            changed = True
                    if changed:
                        workflow["migration_from"] = row["revision_id"]
                        store.save(workflow, row["workflow_id"])

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", identifier):
            raise WorkflowError("Invalid project identifier.")
        target = (self.root / identifier).resolve()
        if target.parent != self.root:
            raise WorkflowError("Project path is outside the workspace.")
        return target

    def create(self, name, identifier=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise WorkflowError("Project name must contain 1–100 characters.")
        identifier = identifier or uuid.uuid4().hex
        target = self.path(identifier)
        with self.lock:
            if (target / "project.json").exists():
                raise WorkflowError("Project already exists.")
            target.mkdir(parents=True, exist_ok=True)
            metadata = {"id":identifier, "name":name.strip(), "created_at":utcnow(), "allowed_modules":list(MODULES), "ai":{"provider":"compatible", "base_url":"https://api.openai.com/v1", "model":"", "key_env":"", "credential_binding":None}}
            atomic_json(target / "project.json", metadata)
            Store(target / "workflows.sqlite3")
        return self.public(identifier)

    def get(self, identifier):
        path = self.path(identifier) / "project.json"
        if not path.is_file():
            raise WorkflowError("Project not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def binding(self, ai):
        return hashlib.sha256((ai["provider"] + "\n" + ai["base_url"]).encode()).hexdigest()

    def public(self, identifier):
        value = self.get(identifier)
        ai = value["ai"]
        if ai.get("key_env"):
            key_set = bool(ai.get("environment_binding")==self.binding(ai) and os.environ.get(ai["key_env"]))
        else:
            key_set = bool((self.path(identifier) / "credential.bin").exists() and ai.get("credential_binding") == self.binding(ai))
        value["ai"] = {key:item for key,item in ai.items() if key not in ("credential_binding","environment_binding")}
        value["ai"]["api_key_set"] = key_set
        value["ai"]["configured"] = bool(ai.get("model")) and (ai["provider"] == "ollama" or key_set)
        return value

    def list(self):
        return [self.public(path.parent.name) for path in sorted(self.root.glob("*/project.json"))]

    def store(self, identifier):
        self.get(identifier)
        store = Store(self.path(identifier) / "workflows.sqlite3")
        store.project_root = self.path(identifier)
        store.project_id = identifier
        return store

    def configure(self, identifier, settings):
        from ai import validate_profile
        if not isinstance(settings, dict):
            raise WorkflowError("AI profile must be an object.")
        with self.lock:
            value = self.get(identifier)
            profile = {**value["ai"], **{key:item for key,item in settings.items() if key in ("provider","base_url","model","key_env")}}
            validate_profile(profile)
            if settings.get("key_env"):
                profile["environment_binding"] = self.binding(profile)
            key = settings.get("api_key")
            if key is not None and (not isinstance(key, str) or len(key) > 8192):
                raise WorkflowError("Invalid API key.")
            if key:
                profile["key_env"] = ""
                profile["environment_binding"] = None
                protected = protect_secret(json.dumps({"key":key,"binding":self.binding(profile)}).encode(), identifier)
                key_path = self.path(identifier) / "credential.bin"
                temporary = key_path.with_name("credential." + uuid.uuid4().hex + ".tmp")
                temporary.write_bytes(protected)
                os.replace(temporary, key_path)
                profile["credential_binding"] = self.binding(profile)
            if settings.get("clear_key"):
                profile["credential_binding"] = None
                profile["key_env"] = ""
            value["ai"] = profile
            atomic_json(self.path(identifier) / "project.json", value)
        return self.public(identifier)

    def key(self, identifier, profile=None):
        profile = profile or self.get(identifier)["ai"]
        if profile.get("key_env") and profile.get("environment_binding")==self.binding(profile):
            return os.environ.get(profile["key_env"], "")
        path = self.path(identifier) / "credential.bin"
        if path.exists() and profile.get("credential_binding") == self.binding(profile):
            value = json.loads(protect_secret(path.read_bytes(), identifier, decrypt=True).decode())
            return value["key"] if value.get("binding")==self.binding(profile) else ""
        return ""

    def connection(self, identifier):
        with self.lock:
            profile = self.get(identifier)["ai"]
            return profile,self.key(identifier,profile)

    def chat_lock(self, identifier):
        self.get(identifier)
        with self.lock:
            return self.chat_locks.setdefault(identifier, threading.Lock())
