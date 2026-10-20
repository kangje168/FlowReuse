import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from engine import demo_workflow, DEMO_INPUT
from server import create_server

ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = ROOT / "work" / "tests"
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        assert Path(cls.temp.name).resolve().is_relative_to(scratch.resolve())
        cls.server = create_server(0, Path(cls.temp.name) / "api.sqlite3")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.client = build_opener(ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def request(self, path, body=None, token=True, extra=None):
        headers = dict(extra or {})
        if body is not None:
            headers["Content-Type"] = "application/json"
            if token:
                headers["X-FlowReuse-Token"] = self.server.csrf
        request = Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            response = self.client.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            return response.status, content, response.headers

    def test_full_save_run_and_reload(self):
        status, body, _ = self.request("/api/workflows", {"workflow":demo_workflow()})
        self.assertEqual(status, 201)
        revision = json.loads(body)
        status, body, _ = self.request("/api/run", {"revision_id":revision["revision_id"],"input":DEMO_INPUT})
        self.assertEqual(status, 200)
        run = json.loads(body)
        self.assertEqual(run["status"], "success")
        self.assertEqual(run["ai_calls"], 0)
        status, loaded, _ = self.request("/api/runs/" + run["id"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(loaded)["outputs"]["node-4"]["net"], "1502.01")

    def test_mutation_requires_local_request_token(self):
        status, _, _ = self.request("/api/workflows", {"workflow":demo_workflow()}, token=False)
        self.assertEqual(status, 403)
        status, _, _ = self.request("/api/workflows", {"workflow":demo_workflow()}, extra={"Origin":"https://example.com"})
        self.assertEqual(status, 403)

    def test_invalid_workflow_is_rejected(self):
        workflow = demo_workflow()
        workflow["nodes"][2]["params"]["percent"] = 999
        status, body, _ = self.request("/api/workflows", {"workflow":workflow})
        self.assertEqual(status, 400)
        self.assertIn("range", json.loads(body)["error"])

    def test_static_files_and_traversal(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"FlowReuse", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for path in ("/../engine.py", "/%2e%2e/engine.py", "/missing.js", "/api/no-such-route"):
            with self.subTest(path=path):
                status, _, _ = self.request(path)
                self.assertEqual(status, 404)

    def test_bad_host_is_rejected(self):
        status, _, _ = self.request("/api/bootstrap", extra={"Host":"attacker.example"})
        self.assertEqual(status, 403)

    def test_first_workspace_is_blank_and_examples_are_optional(self):
        status, body, _ = self.request("/api/bootstrap")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["workspace"]["nodes"], [])
        self.assertEqual(data["input"], {})
        self.assertEqual("New workflow", data["workspace"]["name"])
        self.assertTrue(any(item["category"] == "general" for item in data["templates"]))

    def test_second_server_cannot_shadow_running_service(self):
        with self.assertRaises(OSError):
            create_server(self.server.server_port, Path(self.temp.name) / "second.sqlite3")

    def test_project_headers_prevent_cross_project_revision_and_run_access(self):
        _,body,_=self.request("/api/projects",{"name":"Client A"})
        first=json.loads(body)["project"]["id"]
        _,body,_=self.request("/api/projects",{"name":"Client B"})
        second=json.loads(body)["project"]["id"]
        _,body,_=self.request("/api/workflows",{"workflow":demo_workflow()},extra={"X-FlowReuse-Project":first})
        saved=json.loads(body)
        status,_,_=self.request("/api/revisions/"+saved["revision_id"],extra={"X-FlowReuse-Project":second})
        self.assertEqual(status,404)
        status,_,_=self.request("/api/run",{"revision_id":saved["revision_id"],"input":DEMO_INPUT},extra={"X-FlowReuse-Project":second})
        self.assertEqual(status,400)
        status,body,_=self.request("/api/workflows",extra={"X-FlowReuse-Project":second})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),[])


if __name__ == "__main__":
    unittest.main()
