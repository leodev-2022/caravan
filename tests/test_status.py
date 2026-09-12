import importlib.util
import os
import shutil
import subprocess
import tempfile
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

    def test_onboarding_panel_when_empty(self):
        status = load_status()
        html = status.render({"domain": "example.com", "envs": []}, {}, 0)
        self.assertIn('class="onboard"', html)
        self.assertIn('id="obcmd"', html)
        self.assertNotIn('id="q"', html)

    def test_onboarding_shows_the_ready_invite_command(self):
        status = load_status()
        old = status.REQUESTS_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, "invite.txt"), "w", encoding="utf-8") as fh:
                    fh.write("curl -fsSL x | sudo bash")
                status.REQUESTS_DIR = d
                html = status.render({"domain": "example.com", "envs": []}, {}, 0)
        finally:
            status.REQUESTS_DIR = old
        self.assertIn("curl -fsSL x | sudo bash", html)

    def test_provision_key_shown_only_when_present(self):
        status = load_status()
        with_key = status.render(
            {"domain": "example.com", "envs": [], "provision_pubkey": "ssh-ed25519 AAA"}, {}, 0)
        self.assertIn('id="hubkey"', with_key)
        without = status.render({"domain": "example.com", "envs": []}, {}, 0)
        self.assertNotIn('id="hubkey"', without)

    def test_status_js_is_valid_javascript(self):
        # guards against a broken i18n/handler object silently killing every
        # button (the bug where a missing brace in the I18N dict broke the page)
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        status = load_status()
        fh = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
        try:
            fh.write(status.JS.replace("__REFRESH__", "10"))
            fh.close()
            r = subprocess.run([node, "--check", fh.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
