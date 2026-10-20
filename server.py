"""Local project-isolated application: python server.py --open."""
import argparse
import json
import io
import mimetypes
import secrets
import socket
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

from ai import chat
from engine import catalog, workflow_templates, validate_workflow
from errors import WorkflowError
from projects import ProjectManager
from skill_bundle import refresh_bundle

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "web"


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, value, status=200):
        self.send_bytes(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode())

    def valid_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}

    def project_store(self):
        identifier = self.headers.get("X-FlowReuse-Project","default")
        return self.server.projects.public(identifier), self.server.projects.store(identifier)

    def snapshot(self, project, store, command):
        return refresh_bundle(store,project,command)

    def do_GET(self):
        try:
            if not self.valid_host():
                return self.json_response({"error":"Only local access is allowed."},403)
            path = unquote(urlparse(self.path).path)
            if path.startswith("/api/"):
                project,store = self.project_store()
                if path == "/api/bootstrap":
                    return self.json_response({"modules":[item for item in catalog() if item["id"] in project["allowed_modules"]],"workspace":{"name":"New workflow","nodes":[],"edges":[]},"templates":workflow_templates(),"input":{},"projects":self.server.projects.list(),"project":project,"workflows":store.list_workflows(),"runs":store.list_runs(),"chat":store.chat_history(),"csrf":self.server.csrf,"skill_snapshot":self.snapshot(project,store,"workspace-open")})
                if path == "/api/projects":
                    return self.json_response(self.server.projects.list())
                if path == "/api/workflows":
                    return self.json_response(store.list_workflows())
                if path.startswith("/api/revisions/"):
                    return self.json_response(store.revision(path.split("/")[-1]))
                if path.startswith("/api/workflows/") and path.endswith("/revisions"):
                    return self.json_response(store.list_revisions(path.split("/")[3]))
                if path == "/api/runs":
                    return self.json_response(store.list_runs())
                if path.startswith("/api/runs/"):
                    return self.json_response(store.get_run(path.split("/")[-1]))
                if path == "/api/chat":
                    return self.json_response(store.chat_history())
                if path == "/api/skill/archive":
                    pointer = self.snapshot(project,store,"skill-export")
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as archive:
                        archive.write(pointer["manifest"],"manifest.frskill.json")
                        archive.write(pointer["skill"],"SKILL.md")
                        archive.write(ROOT/"schemas"/"frskill.schema.json","frskill.schema.json")
                    return self.send_bytes(200,buffer.getvalue(),"application/zip")
                if path in ("/api/skill","/api/skill/manifest"):
                    pointer = self.snapshot(project,store,"skill-export")
                    return self.json_response(json.loads(Path(pointer["manifest"]).read_text(encoding="utf-8")) if path.endswith("/manifest") else pointer)
                return self.json_response({"error":"Endpoint not found."},404)
            target = (STATIC/("index.html" if path=="/" else path.lstrip("/"))).resolve()
            if not target.is_relative_to(STATIC) or not target.is_file():
                return self.json_response({"error":"File not found."},404)
            kind = "text/javascript" if target.suffix==".js" else mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_bytes(200,target.read_bytes(),kind+("; charset=utf-8" if target.suffix in (".html",".css",".js",".svg") else ""))
        except WorkflowError as error:
            self.json_response({"error":str(error)},404)
        except Exception:
            self.json_response({"error":"Unable to load this resource."},500)

    def do_POST(self):
        try:
            if not self.valid_host() or self.headers.get("X-FlowReuse-Token")!=self.server.csrf:
                return self.json_response({"error":"Request validation failed. Refresh the page."},403)
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}:
                return self.json_response({"error":"Origin is not allowed."},403)
            if self.headers.get("Content-Type","").split(";")[0]!="application/json":
                return self.json_response({"error":"A JSON request is required."},415)
            length = int(self.headers.get("Content-Length","0"))
            if not 0<length<=2_000_000:
                return self.json_response({"error":"Request is empty or exceeds 2 MB."},413)
            def reject(value):
                raise ValueError("Non-finite JSON numbers are not allowed.")
            body = json.loads(self.rfile.read(length),parse_constant=reject)
            if not isinstance(body,dict):
                raise WorkflowError("Request must be a JSON object.")
            path = urlparse(self.path).path
            project,store = self.project_store()
            if path == "/api/projects":
                created = self.server.projects.create(body.get("name"))
                snapshot = self.snapshot(created,self.server.projects.store(created["id"]),"project-create")
                return self.json_response({"project":created,"skill_snapshot":snapshot},201)
            if path == "/api/project/ai":
                updated = self.server.projects.configure(project["id"],body)
                return self.json_response({"project":updated,"skill_snapshot":self.snapshot(updated,store,"ai-configure")})
            if path == "/api/chat":
                result = chat(self.server.projects,project["id"],body,"fr" if self.headers.get("X-FlowReuse-Language")=="fr" else "en")
                result["skill_snapshot"] = self.snapshot(project,store,"ai-chat")
                return self.json_response(result)
            if path == "/api/validate":
                _,_,_,order = validate_workflow(body.get("workflow"))
                return self.json_response({"valid":True,"order":order})
            if path == "/api/workflows":
                workflow = body.get("workflow")
                validate_workflow(workflow)
                if any(node["module"] not in project["allowed_modules"] for node in workflow["nodes"]):
                    raise WorkflowError("Module is not enabled in this project.")
                result = store.save(workflow,body.get("workflow_id"))
                result["skill_snapshot"] = self.snapshot(project,store,"workflow-save")
                return self.json_response(result,201)
            if path == "/api/run":
                if not isinstance(body.get("revision_id"),str):
                    raise WorkflowError("Save a workflow revision first.")
                result = store.run(body["revision_id"],body.get("input"))
                result["skill_snapshot"] = self.snapshot(project,store,"workflow-run")
                return self.json_response(result)
            return self.json_response({"error":"Endpoint not found."},404)
        except (WorkflowError,ValueError,TypeError) as error:
            self.json_response({"error":str(error)},400)
        except Exception:
            self.json_response({"error":"Operation failed. No credentials are included in error responses."},500)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False
    def server_bind(self):
        if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def create_server(port=8765,database=None,project_root=None):
    server = LocalServer(("127.0.0.1",port),Handler)
    try:
        server.projects = ProjectManager(project_root or (Path(database).parent/"projects" if database else ROOT/"data"/"projects"),legacy_database=database or ROOT/"data"/"flowreuse.sqlite3")
        server.store = server.projects.store("default")
        server.csrf = secrets.token_urlsafe(32)
        server.daemon_threads = True
        return server
    except Exception:
        server.server_close()
        raise


if __name__=="__main__":
    parser = argparse.ArgumentParser(description="FlowReuse local AI workflow workspace")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--open",action="store_true",help="Open the default browser after starting")
    options = parser.parse_args()
    server = create_server(options.port)
    print(f"FlowReuse ready: http://127.0.0.1:{server.server_port}",flush=True)
    if options.open:
        import threading
        import webbrowser
        threading.Timer(.5,lambda:webbrowser.open(f"http://127.0.0.1:{server.server_port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
