import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_apply():
    spec = importlib.util.spec_from_file_location(
        "apply_request", os.path.join(ROOT, "tools", "apply_request.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplyRequestTest(unittest.TestCase):
    def setUp(self):
        self.apply = load_apply()

    def test_add_new(self):
        envs, changed = self.apply.apply_one([], {"action": "add", "env": {"name": "web1", "ip": "100.64.0.10", "port": 9898}})
        self.assertTrue(changed)
        self.assertEqual([e["name"] for e in envs], ["web1"])

    def test_add_updates_existing(self):
        envs, changed = self.apply.apply_one(
            [{"name": "web1", "ip": "10.0.0.1"}],
            {"action": "add", "env": {"name": "web1", "ip": "10.0.0.2"}},
        )
        self.assertTrue(changed)
        self.assertEqual(len(envs), 1)
        self.assertEqual(envs[0]["ip"], "10.0.0.2")

    def test_rename_replaces_old_name(self):
        envs, changed = self.apply.apply_one(
            [{"name": "win1", "ip": "10.0.0.1"}],
            {"action": "add", "env": {"name": "SKUD", "ip": "10.0.0.1"}, "original_name": "win1"},
        )
        self.assertTrue(changed)
        self.assertEqual([e["name"] for e in envs], ["SKUD"])

    def test_rename_keeps_engine(self):
        envs, _ = self.apply.apply_one(
            [{"name": "win1", "ip": "10.0.0.1", "engine": "opencode"}],
            {"action": "add", "env": {"name": "SKUD", "ip": "10.0.0.1"}, "original_name": "win1"},
        )
        self.assertEqual(envs[0]["engine"], "opencode")

    def test_edit_clears_engine_when_empty(self):
        envs, _ = self.apply.apply_one(
            [{"name": "web1", "ip": "10.0.0.1", "engine": "opencode"}],
            {"action": "add", "env": {"name": "web1", "ip": "10.0.0.1", "engine": ""}},
        )
        self.assertNotIn("engine", envs[0])

    def test_delete(self):
        envs, changed = self.apply.apply_one(
            [{"name": "web1"}, {"name": "work"}], {"action": "delete", "name": "web1"}
        )
        self.assertTrue(changed)
        self.assertEqual([e["name"] for e in envs], ["work"])

    def test_delete_missing_is_noop(self):
        envs, changed = self.apply.apply_one([{"name": "web1"}], {"action": "delete", "name": "nope"})
        self.assertFalse(changed)
        self.assertEqual(len(envs), 1)

    def test_bad_request_is_noop(self):
        envs, changed = self.apply.apply_one([], {"action": "add", "env": {}})
        self.assertFalse(changed)
        self.assertEqual(envs, [])


if __name__ == "__main__":
    unittest.main()
