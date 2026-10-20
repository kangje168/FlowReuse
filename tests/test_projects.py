import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from ai import chat, materialize_plan
from cli import export_output
from engine import compose_workflow
from errors import WorkflowError
from projects import ProjectManager, protect_secret
from skill_bundle import refresh_bundle

ROOT=Path(__file__).resolve().parents[1]
PLAN={"message":"I connected the input, field extraction and formatting steps.","plan":{"name":"Reusable extraction","nodes":[{"id":"input","module":"input_data"},{"id":"extract","module":"pick_field","params":{"path":"items"}},{"id":"text","module":"format_json"}],"edges":[{"source":"input","target":"extract"},{"source":"extract","target":"text"}]},"missing_capabilities":[]}


class ModelStub(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path":self.path,"body":body,"authorization":self.headers.get("Authorization")})
        content=json.dumps(self.server.answer)
        value={"message":{"content":content},"choices":[{"message":{"content":content}}],"usage":{"total_tokens":42}}
        data=json.dumps(value).encode()
        self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        scratch=ROOT/"work"/"tests";scratch.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch)
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(scratch.resolve()))
        self.manager=ProjectManager(Path(self.temp.name)/"projects")
        self.first=self.manager.create("Project A")
        self.second=self.manager.create("Project B")

    def tearDown(self):
        self.temp.cleanup()

    def test_workflows_runs_and_conversations_are_isolated(self):
        first=self.manager.store(self.first["id"]);second=self.manager.store(self.second["id"])
        saved=first.save(compose_workflow("Count",[{"module":"input_data"},{"module":"count_items"}]))
        run=first.run(saved["revision_id"],[1,2])
        first.add_chat("user","Private project A request")
        self.assertEqual(second.list_workflows(),[])
        self.assertEqual(second.list_runs(),[])
        self.assertEqual(second.chat_history(),[])
        with self.assertRaises(WorkflowError):second.revision(saved["revision_id"])
        with self.assertRaises(WorkflowError):second.get_run(run["id"])
        with self.assertRaises(WorkflowError):second.run(saved["revision_id"],[])

    def test_output_cannot_escape_project(self):
        first=self.manager.store(self.first["id"])
        saved=first.save(compose_workflow("Input",[{"module":"input_data"}]))
        run=first.run(saved["revision_id"],{"value":1})
        with self.assertRaises(WorkflowError):export_output(first,run,self.manager.path(self.second["id"])/"outputs"/"stolen.json")
        target=export_output(first,run,self.manager.path(self.first["id"])/"outputs"/"result.json")
        self.assertTrue(target.exists())

    def test_profiles_and_secrets_do_not_cross_projects_or_destinations(self):
        with patch.dict(os.environ,{"FLOWREUSE_TEST_KEY":"test-only-not-a-real-key"}):
            self.manager.configure(self.first["id"],{"provider":"compatible","base_url":"https://example.com/v1","model":"model-a","key_env":"FLOWREUSE_TEST_KEY"})
            self.assertTrue(self.manager.public(self.first["id"])["ai"]["configured"])
            self.assertFalse(self.manager.public(self.second["id"])["ai"]["configured"])
            self.assertEqual(self.manager.key(self.second["id"]),"")
            store=self.manager.store(self.first["id"])
            snapshot=refresh_bundle(store,self.manager.public(self.first["id"]))
            content=Path(snapshot["manifest"]).read_text()+Path(snapshot["skill"]).read_text()
            self.assertNotIn("test-only-not-a-real-key",content)
            self.assertNotIn("FLOWREUSE_TEST_KEY",content)

    @unittest.skipUnless(os.name=="nt","Windows DPAPI only")
    def test_dpapi_round_trip_is_bound_to_project_and_endpoint(self):
        identifier=self.first["id"]
        encrypted=protect_secret(b"fake-key-for-testing",identifier)
        self.assertNotIn(b"fake-key",encrypted)
        self.assertEqual(protect_secret(encrypted,identifier,decrypt=True),b"fake-key-for-testing")
        with self.assertRaises(WorkflowError):protect_secret(encrypted,self.second["id"],decrypt=True)
        self.manager.configure(identifier,{"model":"test","api_key":"fake-key-for-testing"})
        self.assertEqual(self.manager.key(identifier),"fake-key-for-testing")
        self.manager.configure(identifier,{"base_url":"https://another.example/v1"})
        self.assertEqual(self.manager.key(identifier),"")
        self.manager.configure(identifier,{"key_env":"FLOWREUSE_MISSING_KEY"})
        self.assertFalse(self.manager.public(identifier)["ai"]["configured"])
        self.manager.configure(identifier,{"api_key":"typed-test-key"})
        self.assertEqual(self.manager.key(identifier),"typed-test-key")
        self.assertTrue(self.manager.public(identifier)["ai"]["configured"])

    def test_snapshot_tracks_latest_revision_without_business_rows(self):
        store=self.manager.store(self.first["id"])
        workflow=compose_workflow("Input",[{"module":"input_data"}])
        saved=store.save(workflow)
        store.run(saved["revision_id"],{"private":"DO-NOT-EXPORT"})
        one=refresh_bundle(store,self.first,"run")
        two=refresh_bundle(store,self.first,"discover")
        self.assertNotEqual(one["generation"],two["generation"])
        manifest=json.loads(Path(two["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["project"]["id"],self.first["id"])
        self.assertEqual(manifest["workflows"][0]["revision_id"],saved["revision_id"])
        self.assertNotIn("DO-NOT-EXPORT",json.dumps(manifest))
        self.assertEqual(manifest["execution"]["model_calls_on_success"],0)

    def test_cli_refreshes_skill_on_success_and_failure(self):
        base=[sys.executable,str(ROOT/"cli.py"),"--projects-root",str(self.manager.root),"--project",self.first["id"]]
        first=subprocess.run([*base,"discover"],capture_output=True,text=True,encoding="utf-8")
        second=subprocess.run([*base,"describe","--revision","missing"],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(second.returncode,1,second.stderr)
        a,b=json.loads(first.stdout),json.loads(second.stdout)
        self.assertNotEqual(a["skill_snapshot"]["generation"],b["skill_snapshot"]["generation"])
        self.assertEqual(b["project_id"],self.first["id"])

    def test_invalid_project_path_is_rejected(self):
        for identifier in ("../default","A/B","..","C:\\outside"):
            with self.subTest(identifier=identifier),self.assertRaises(WorkflowError):self.manager.get(identifier)

    def test_ai_generated_unknown_or_incompatible_modules_are_rejected(self):
        bad={"name":"bad","nodes":[{"id":"a","module":"invented_python"}],"edges":[]}
        with self.assertRaises(WorkflowError):materialize_plan(bad,list(self.first["allowed_modules"]))
        bad={"name":"bad","nodes":[{"id":"a","module":"input_data"},{"id":"b","module":"replace_text"}],"edges":[{"source":"a","target":"b"}]}
        with self.assertRaises(WorkflowError):materialize_plan(bad,list(self.first["allowed_modules"]))

    def test_real_transport_builds_dag_and_successful_rerun_does_not_call_model(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),ModelStub)
        server.requests=[];server.answer=PLAN
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            self.manager.configure(self.first["id"],{"provider":"ollama","base_url":f"http://127.0.0.1:{server.server_port}","model":"test-model"})
            result=chat(self.manager,self.first["id"],{"message":"Extract items and format as text"},"fr")
            self.assertEqual(len(result["workflow"]["nodes"]),3)
            self.assertEqual(len(result["workflow"]["edges"]),2)
            self.assertEqual(result["ai_calls"],1)
            self.assertEqual(server.requests[0]["path"],"/api/chat")
            self.assertIn("French",server.requests[0]["body"]["messages"][0]["content"])
            store=self.manager.store(self.first["id"])
            run=store.run(result["saved"]["revision_id"],{"items":[1,2,3],"private":"NEVER-SEND-THIS"})
            self.assertEqual(run["status"],"success")
            self.assertEqual(run["ai_calls"],0)
            self.assertEqual(len(server.requests),1)
            self.assertNotIn("NEVER-SEND-THIS",json.dumps(server.requests))
            self.assertEqual(self.manager.store(self.second["id"]).chat_history(),[])
            with patch.dict(os.environ,{"FLOWREUSE_TEST_KEY":"test-only"}):
                self.manager.configure(self.second["id"],{"provider":"compatible","base_url":f"http://127.0.0.1:{server.server_port}/v1","model":"second-model","key_env":"FLOWREUSE_TEST_KEY"})
                result=chat(self.manager,self.second["id"],{"message":"Build an extraction workflow"})
                self.assertEqual(result["ai_calls"],1)
                self.assertEqual(server.requests[-1]["path"],"/v1/chat/completions")
                self.assertEqual(server.requests[-1]["authorization"],"Bearer test-only")
                self.assertFalse(server.requests[-1]["body"]["store"])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=="__main__":unittest.main()
