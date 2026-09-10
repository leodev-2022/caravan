import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_status():
    spec = importlib.util.spec_from_file_location("status", os.path.join(ROOT, "status.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_data():
    return {
        "domain": "example.com",
        "auth_url": "https://auth.example.com",
        "envs": [
            {
                "name": "web1",
                "aliases": ["w1"],
                "hosts": ["web1", "w1"],
                "ip": "100.64.0.10",
                "port": 9898,
                "label": "Web server",
                "location": "DC1",
                "tags": ["dev"],
            }
        ],
    }


class StatusTest(unittest.TestCase):
    def test_render_contains_env_and_domain(self):
        status = load_status()
        html = status.render(sample_data(), {"web1": {"status": "online", "ms": 3}}, 0)
        self.assertIn("web1", html)
        self.assertIn("example.com", html)

    def test_render_handles_offline(self):
        status = load_status()
        html = status.render(sample_data(), {"web1": {"status": "offline", "ms": 0}}, 0)
        self.assertIn("web1", html)


if __name__ == "__main__":
    unittest.main()
