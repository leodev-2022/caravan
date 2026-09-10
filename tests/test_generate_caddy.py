import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render(tmp, extra_env=None):
    shutil.copy(os.path.join(ROOT, "generate_caddy.py"), tmp)
    shutil.copy(os.path.join(ROOT, "caravan.env.example"), os.path.join(tmp, "caravan.env"))
    shutil.copy(os.path.join(ROOT, "conf", "nodes.example.yaml"), os.path.join(tmp, "nodes.yaml"))
    env = dict(os.environ)
    env.update(extra_env or {})
    subprocess.run([sys.executable, "generate_caddy.py"], cwd=tmp, check=True, env=env)
    with open(os.path.join(tmp, "caddy", "Caddyfile"), encoding="utf-8") as fh:
        return fh.read()


class GenerateCaddyTest(unittest.TestCase):
    def test_renders_example_domain_and_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            caddy = render(tmp)
            for line in (
                "example.com {",
                "hub.example.com {",
                "mesh.example.com {",
                "auth.example.com {",
                "web1.example.com {",
                "w1.example.com {",  # alias of web1
                "reverse_proxy http://100.64.0.10:9898",
            ):
                self.assertIn(line, caddy)
            # every domain in the file must be on the example domain
            domains = set(re.findall(r"[a-z0-9.-]+\.(?:com|net|org|io)", caddy))
            self.assertTrue(domains, "no domains found")
            self.assertTrue(all(d.endswith("example.com") for d in domains), domains)

            with open(os.path.join(tmp, "nodes.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["domain"], "example.com")
            self.assertEqual(data["auth_url"], "https://auth.example.com")
            self.assertIn("web1", [e["name"] for e in data["envs"]])

    def test_tls_internal_adds_local_certs(self):
        with tempfile.TemporaryDirectory() as tmp:
            caddy = render(tmp, {"TLS_MODE": "internal"})
            self.assertIn("local_certs", caddy)

    def test_domain_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            caddy = render(tmp, {"DOMAIN": "test.example.org", "EMAIL": "admin@test.example.org"})
            self.assertIn("test.example.org {", caddy)
            self.assertIn("hub.test.example.org {", caddy)
            self.assertNotIn("example.com", caddy)


if __name__ == "__main__":
    unittest.main()
