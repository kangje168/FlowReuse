import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from engine import DEMO_INPUT, MODULES, Store, WorkflowError, demo_workflow, compose_workflow, validate_workflow
from cli import compact_result, failure_context

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work" / "tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(scratch.resolve()))
        self.store = Store(Path(self.temp.name) / "test.sqlite3")
        self.workflow = demo_workflow()
        self.saved = self.store.save(self.workflow)

    def tearDown(self):
        self.temp.cleanup()

    def test_rerun_new_input_without_model(self):
        first = self.store.run(self.saved["revision_id"], DEMO_INPUT)
        second = self.store.run(self.saved["revision_id"], [{"id": "NEW", "amount": 100}])
        self.assertEqual(first["status"], "success")
        self.assertEqual(first["outputs"]["node-4"]["net"], "1502.01")
        self.assertEqual(second["outputs"]["node-4"]["net"], "90.00")
        self.assertEqual(second["outputs"]["node-4"]["count"], 1)
        self.assertEqual(first["ai_calls"] + second["ai_calls"], 0)
        self.assertNotEqual(first["id"], second["id"])

    def test_revision_is_immutable_and_shared_code_is_unchanged(self):
        modified = copy.deepcopy(self.workflow)
        modified["nodes"][2]["params"]["percent"] = 20
        new = self.store.save(modified, self.saved["workflow_id"])
        original = self.store.run(self.saved["revision_id"], [{"id": "A", "amount": 100}])
        changed = self.store.run(new["revision_id"], [{"id": "A", "amount": 100}])
        self.assertEqual(new["number"], 2)
        self.assertEqual(original["outputs"]["node-4"]["net"], "90.00")
        self.assertEqual(changed["outputs"]["node-4"]["net"], "80.00")
        self.assertEqual(MODULES["discount_orders"]["defaults"]["percent"], 10)

    def test_failure_handoff_then_field_mapping_repair(self):
        data = [{"id": "PRIVATE-CUSTOMER-ORDER", "total": 250, "secret": "DO-NOT-RETURN"}]
        failed = self.store.run(self.saved["revision_id"], data)
        context = failure_context(self.store, failed)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual([node["status"] for node in failed["nodes"]], ["success", "failed", "skipped", "skipped"])
        self.assertTrue(context["requires_ai"])
        self.assertEqual(context["upstream_schema"]["item"]["fields"]["total"], "int")
        self.assertNotIn("DO-NOT-RETURN", json.dumps(context))
        self.assertNotIn("PRIVATE-CUSTOMER-ORDER", json.dumps(context))
        self.workflow["nodes"][1]["params"]["amount_field"] = "total"
        saved = self.store.save(self.workflow, self.saved["workflow_id"])
        recovered = self.store.run(saved["revision_id"], data)
        self.assertEqual(recovered["status"], "success")
        self.assertEqual(recovered["outputs"]["node-4"]["net"], "225.00")
        self.assertEqual(self.store.get_run(failed["id"])["status"], "failed")

    def test_money_rounding_and_threshold(self):
        self.workflow["nodes"][2]["params"] = {"percent": 10, "minimum": 100}
        saved = self.store.save(self.workflow)
        run = self.store.run(saved["revision_id"], [{"id":"A","amount":"0.105"},{"id":"B","amount":"100.05"}])
        report = run["outputs"]["node-4"]
        self.assertEqual(report["gross"], "100.16")
        self.assertEqual(report["discount"], "10.01")
        self.assertEqual(report["net"], "90.15")

    def test_bad_amounts_fail_without_downstream_execution(self):
        for value in (None, True, -1, "NaN", "Infinity", "not money", "1000000001"):
            with self.subTest(value=value):
                run = self.store.run(self.saved["revision_id"], [{"id":"A","amount":value}])
                self.assertEqual(run["status"], "failed")
                self.assertEqual(run["nodes"][-1]["status"], "skipped")

    def test_duplicate_order_ids_fail(self):
        run = self.store.run(self.saved["revision_id"], [{"id":"A","amount":10},{"id":"A","amount":20}])
        self.assertEqual(run["status"], "failed")
        self.assertIn("duplicate", run["error"]["message"])

    def test_compact_success_omits_rows_and_code(self):
        run = self.store.run(self.saved["revision_id"], DEMO_INPUT)
        compact = compact_result(self.store, run, Path("output.json"))
        text = json.dumps(compact)
        self.assertLess(len(text), 1000)
        self.assertNotIn("ORD-1001", text)
        self.assertNotIn("source", compact)
        self.assertFalse(compact["requires_ai"])

    def test_fanout_and_layout_do_not_change_execution_order(self):
        duplicate = copy.deepcopy(self.workflow["nodes"][2])
        duplicate["id"] = "discount-2"
        duplicate["x"], duplicate["y"] = -1000, -2000
        duplicate["params"]["percent"] = 50
        self.workflow["nodes"].append(duplicate)
        self.workflow["edges"].append({"id":"branch", "source":"node-2", "target":"discount-2"})
        saved = self.store.save(self.workflow)
        run = self.store.run(saved["revision_id"], [{"id":"A","amount":100}])
        self.assertEqual(run["status"], "success")
        self.assertEqual(run["outputs"]["discount-2"][0]["net"], "50.00")
        self.assertEqual(run["outputs"]["node-4"]["net"], "90.00")

    def test_rejects_unknown_module_and_modified_code_fingerprint(self):
        for change in (lambda n:n.update(module="exec_user_code"),lambda n:n.update(hash="tampered"),lambda n:n.update(version="9.0")):
            workflow = copy.deepcopy(self.workflow)
            change(workflow["nodes"][0])
            with self.assertRaises(WorkflowError):
                self.store.save(workflow)

    def test_invalid_edges_and_parameters(self):
        variants = []
        missing = copy.deepcopy(self.workflow); missing["edges"].pop(); variants.append(missing)
        badtype = copy.deepcopy(self.workflow); badtype["edges"][0]["target"] = "node-4"; variants.append(badtype)
        duplicate = copy.deepcopy(self.workflow); duplicate["edges"].append(copy.deepcopy(duplicate["edges"][0])); variants.append(duplicate)
        selfedge = copy.deepcopy(self.workflow); selfedge["edges"][0]["target"] = "node-1"; variants.append(selfedge)
        badparams = copy.deepcopy(self.workflow); badparams["nodes"][2]["params"]["percent"] = 101; variants.append(badparams)
        boolparams = copy.deepcopy(self.workflow); boolparams["nodes"][2]["params"]["percent"] = True; variants.append(boolparams)
        nanparams = copy.deepcopy(self.workflow); nanparams["nodes"][2]["params"]["percent"] = float("nan"); variants.append(nanparams)
        for workflow in variants:
            with self.subTest(workflow=workflow):
                with self.assertRaises(WorkflowError):
                    validate_workflow(workflow)

    def test_cli_exit_codes_and_skill_wrapper(self):
        input_path = Path(self.temp.name) / "input.json"
        input_path.write_text(json.dumps(DEMO_INPUT), encoding="utf-8")
        wrapper = ROOT / ".agents/skills/flowreuse-run/scripts/run_flowreuse.py"
        command = [sys.executable, str(wrapper), "--db", str(self.store.path), "run", "--revision", self.saved["revision_id"], "--input", str(input_path)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["requires_ai"])
        input_path.write_text('[{"id":"A","unexpected":100}]', encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(json.loads(result.stdout)["requires_ai"])

    def test_database_persists_across_instances(self):
        run = self.store.run(self.saved["revision_id"], DEMO_INPUT)
        other = Store(self.store.path)
        self.assertEqual(other.list_workflows()[0]["revision_id"], self.saved["revision_id"])
        self.assertEqual(other.get_run(run["id"])["status"], "success")

    def test_compose_fills_versions_defaults_and_connections(self):
        steps = [{"module":"read_orders"},{"module":"validate_orders"},{"module":"discount_orders","params":{"percent":15}},{"module":"summarize_orders"}]
        workflow = compose_workflow("15% discount", steps)
        self.assertEqual(len(workflow["edges"]), 3)
        self.assertEqual(workflow["nodes"][2]["params"], {"percent":15,"minimum":0})
        saved = self.store.save(workflow)
        run = self.store.run(saved["revision_id"], [{"id":"A","amount":100}])
        self.assertEqual(run["outputs"]["node-4"]["net"], "85.00")
        with self.assertRaises(WorkflowError):
            compose_workflow("Invalid connection", [{"module":"read_orders"},{"module":"summarize_orders"}])

    def test_cli_adapt_and_retry_without_exposing_stored_input(self):
        data = [{"id":"PRIVATE","total":100}]
        failed = self.store.run(self.saved["revision_id"], data)
        base = [sys.executable, str(ROOT / "cli.py"), "--db", str(self.store.path)]
        adapted = subprocess.run([*base, "adapt", "--revision", self.saved["revision_id"], "--node", "node-2", "--params", '{"amount_field":"total"}', "--fork-name", "Orders with total field"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(adapted.returncode, 0, adapted.stdout + adapted.stderr)
        saved = json.loads(adapted.stdout)
        self.assertNotEqual(saved["workflow_id"], self.saved["workflow_id"])
        retried = subprocess.run([*base, "retry", "--run", failed["id"], "--revision", saved["revision_id"]], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
        compact = json.loads(retried.stdout)
        self.assertEqual(compact["summary"][0]["net"], "90.00")
        self.assertNotIn("PRIVATE", retried.stdout)
        self.assertEqual(self.store.get_run(compact["run_id"])["retry_of"], failed["id"])


if __name__ == "__main__":
    unittest.main()
