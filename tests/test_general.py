import json
from pathlib import Path
import tempfile
import unittest

from cli import compact_result
from engine import MODULES, Store, WorkflowError, catalog, compose_workflow, demo_workflow, register_modules, workflow_templates

ROOT = Path(__file__).resolve().parents[1]


class GeneralWorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work" / "tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(scratch.resolve()))
        self.store = Store(Path(self.temp.name) / "general.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, steps, data):
        saved = self.store.save(compose_workflow("Domain-independent workflow", steps))
        return self.store.run(saved["revision_id"], data)

    def test_extract_and_format_arbitrary_json_without_order_fields(self):
        run = self.execute([{"module":"input_data"},{"module":"pick_field","params":{"path":"results.0"}},{"module":"format_json"}], {"results":[{"project":"Example","ready":True}]})
        self.assertEqual(run["status"], "success")
        self.assertEqual(json.loads(run["outputs"]["node-3"]), {"project":"Example","ready":True})
        self.assertEqual(run["ai_calls"], 0)

    def test_text_replacement_can_delete_and_split(self):
        run = self.execute([{"module":"input_data"},{"module":"format_json","params":{"indent":0}},{"module":"replace_text","params":{"search":"OLD","replacement":""}},{"module":"split_text","params":{"separator":","}}], ["OLD A","OLD B"])
        self.assertEqual(run["status"], "success")
        self.assertEqual(len(run["outputs"]["node-4"]), 2)
        self.assertNotIn("OLD", str(run["outputs"]))

    def test_count_and_arbitrary_net_field_do_not_trigger_order_summary(self):
        run = self.execute([{"module":"input_data"},{"module":"count_items"}], ["a","b","c"])
        self.assertEqual(run["outputs"]["node-2"], {"count":3,"kind":"array"})
        generic = self.execute([{"module":"input_data"}], {"net":"not-a-price"})
        result = compact_result(self.store, generic)
        self.assertEqual(result["status"], "success")
        self.assertIn("schema", result["summary"][0])

    def test_optional_order_template_does_not_expand_with_registry(self):
        self.assertEqual(len(demo_workflow()["nodes"]), 4)
        self.assertEqual(len([item for item in catalog() if item["category"] == "general"]), 6)
        self.assertEqual(len([item for item in catalog() if item["category"] == "example"]), 4)
        for template in workflow_templates():
            saved = self.store.save(template["workflow"])
            self.assertEqual(self.store.run(saved["revision_id"], template["input"])["status"], "success")

    def test_missing_path_stops_and_wrong_text_type_fails(self):
        run = self.execute([{"module":"input_data"},{"module":"pick_field"},{"module":"format_json"}], {"something_else":123})
        self.assertEqual(run["nodes"][-1]["status"], "skipped")
        with self.assertRaisesRegex(ValueError, "string"):
            MODULES["replace_text"]["function"]([], {"search":"a","replacement":"b"})

    def test_registration_cannot_override_existing_implementation(self):
        original = MODULES["input_data"]
        with self.assertRaises(WorkflowError):
            register_modules({"input_data":original})
        self.assertIs(MODULES["input_data"], original)


if __name__ == "__main__":
    unittest.main()
