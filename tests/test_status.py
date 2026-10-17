import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

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
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(status.JS.replace("__REFRESH__", "10"))
            path = fh.name
        try:
            r = subprocess.run([node, "--check", path], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            os.unlink(path)


class HandoffTest(unittest.TestCase):
    """The board is the agents<->human mailbox; its routing rules must be exact."""

    def setUp(self):
        self.status = load_status()
        self.status.HANDOFF_NOTIFY = True
        self.dir = tempfile.mkdtemp()
        self.status.HANDOFF_FILE = os.path.join(self.dir, "handoff.jsonl")
        self.status.HANDOFF_SEEN_FILE = os.path.join(self.dir, "handoff-seen.json")
        self.sent = []
        self.status.notify = lambda text, buttons=None: (self.sent.append(text), True)[1]
        # Run the ping thread inline so the assertions are deterministic.
        self._real_threading = self.status.threading
        outer = self

        class _Inline:
            def __init__(self, target=None, args=(), daemon=None, **kw):
                outer._target, outer._args = target, args

            def start(self):
                outer._target(*outer._args)

        class _Shim:
            Thread = _Inline

        self.status.threading = _Shim()

    def tearDown(self):
        self.status.threading = self._real_threading
        shutil.rmtree(self.dir, ignore_errors=True)

    def ping(self, frm, topic, to):
        return self.status.handoff_ping_reason({"from": frm, "topic": topic, "to": to})

    def test_targets_accepts_string_and_list(self):
        t = self.status.handoff_targets
        self.assertEqual(t("admin"), ["admin"])
        self.assertEqual(t(["admin"]), ["admin"])
        self.assertEqual(t("dev, admin"), ["dev", "admin"])
        self.assertEqual(t(["dev", "user"]), ["dev", "user"])
        self.assertEqual(t(" dev ; admin "), ["dev", "admin"])
        self.assertEqual(t(["ALL"]), ["all"])

    def test_actor_list_is_configurable_via_env(self):
        # the published default is the generic trio; a hub extends it locally
        os.environ["HANDOFF_ACTORS"] = "dev,admin,user,zeta"
        try:
            st = load_status()
            self.assertEqual(st.HANDOFF_ACTORS[-1], "zeta")
            self.assertEqual(st.handoff_targets("zeta"), ["zeta"])
            self.assertIn('<option value="zeta">zeta</option>', st.render_handoff())
        finally:
            del os.environ["HANDOFF_ACTORS"]

    def test_unknown_recipient_is_an_error_not_a_silent_all(self):
        t = self.status.handoff_targets
        with self.assertRaises(ValueError):
            t("manager")
        with self.assertRaises(ValueError):
            t(["dev", "nope"])

    def test_empty_to_means_everyone(self):
        t = self.status.handoff_targets
        self.assertEqual(t(""), ["all"])
        self.assertEqual(t(None), ["all"])

    def test_audience_is_human_readable(self):
        a = self.status.handoff_audience
        self.assertEqual(a(["user"]), "вам")
        self.assertEqual(a(["all"]), "всем")
        self.assertEqual(a(["dev"]), "dev")
        self.assertEqual(a(["dev", "user"]), "dev, вам")

    def test_only_the_human_gets_pinged(self):
        self.assertEqual(self.ping("dev", "note", ["admin"]), "agents-only")
        self.assertEqual(self.ping("admin", "note", ["dev"]), "agents-only")
        self.assertEqual(self.ping("dev", "note", ["user"]), "ping")
        self.assertEqual(self.ping("dev", "ask", ["all"]), "ping")
        self.assertEqual(self.ping("admin", "warn", ["dev"]), "ping")
        self.assertEqual(self.ping("user", "ask", ["all"]), "off")

    def test_mute_silences_the_human_but_not_a_warn(self):
        self.status.handoff_mute(hours=2)
        self.assertEqual(self.ping("dev", "ask", ["user"]), "muted")
        self.assertEqual(self.ping("admin", "warn", ["dev"]), "ping")

    def test_notify_switch_off_silences_everything(self):
        self.status.HANDOFF_NOTIFY = False
        self.assertEqual(self.ping("dev", "warn", ["user"]), "off")

    def test_add_pings_the_human_and_stays_quiet_for_agents(self):
        self.status.handoff_add("dev", "done", "для тебя", to="user")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("→ вам", self.sent[0])
        self.assertIn("для тебя", self.sent[0])
        self.status.handoff_add("dev", "note", "просто агентам", to=["admin"])
        self.assertEqual(len(self.sent), 1)  # no second ping

    def test_add_rejects_a_bad_recipient_without_writing(self):
        with self.assertRaises(ValueError):
            self.status.handoff_add("dev", "note", "текст", to="manager")
        self.assertEqual(self.status.handoff_load(), [])

    def test_unread_tracks_mail_addressed_to_the_human(self):
        self.status.handoff_add("dev", "ask", "вопрос к тебе", to="user")
        self.status.handoff_add("dev", "note", "агентам", to="admin")
        self.assertEqual(self.status.handoff_unread("user")[2], 1)
        self.assertEqual(self.status.handoff_unread("admin")[2], 1)
        with self.assertRaises(ValueError):
            self.status.handoff_ack("nobody")

    def test_handoff_page_marks_posts_new_or_read(self):
        st = self.status
        st.handoff_add("dev", "note", "старая запись", to="admin")
        st.handoff_ack("user")                       # the person has read up to here
        st.handoff_add("dev", "ask", "вопрос к тебе", to="user")
        st.handoff_add("user", "note", "это я сам написал", to="all")
        html = st.render_handoff()
        self.assertIn("Новых для вас: <b>1</b>", html)   # the person's own note does not count
        self.assertIn("✓ отметить всё прочитанным", html)
        self.assertIn('class="hstate new"', html)     # the fresh post…
        self.assertIn('class="hstate read"', html)    # …and the one already read
        self.assertIn("→ вам", html)
        self.assertIn("→ admin", html)
        # no "who owes whom" accounting on the page anymore
        self.assertNotIn("Адресовано и не прочитано", html)
        self.assertNotIn("dev — ", html)

    def test_handoff_page_when_everything_is_read(self):
        st = self.status
        st.handoff_add("dev", "note", "уже прочитано", to="user")
        st.handoff_ack("user")
        html = st.render_handoff()
        self.assertIn("У вас всё прочитано", html)
        self.assertNotIn('id="hf-ack"', html)         # nothing new -> no acknowledge button


class EngineAlertTest(unittest.TestCase):
    """A node whose engine is dead must be visible (and alerted) even though the
    metrics agent keeps the card 'online' — that's the 6.56 stuck-node case."""

    def setUp(self):
        self.status = load_status()
        self.sent = []
        self.status.notify = lambda text, buttons=None: (self.sent.append(text), True)[1]

    def test_classify_engine(self):
        c = self.status.classify_engine
        self.assertEqual(c(True, 4000), "ok")
        self.assertEqual(c(False, 3), "down")      # refused instantly: nothing listening
        self.assertEqual(c(False, 4000), "busy")   # connected, but slow / timed out

    def test_render_shows_the_down_chip(self):
        html = self.status.render(sample_data(), {"web1": {"status": "online", "ms": 0,
                                                           "engine": "down"}}, 0)
        self.assertIn('data-i18n="engdown"', html)
        self.assertIn("движок не отвечает", html)

    def test_render_shows_the_busy_chip(self):
        html = self.status.render(sample_data(), {"web1": {"status": "online", "ms": 0,
                                                           "engine": "busy"}}, 0)
        self.assertIn('data-i18n="engbusy"', html)
        self.assertIn("движок занят", html)
        self.assertNotIn('data-i18n="engdown"', html)

    def test_alerts_once_on_a_down_engine_and_notes_recovery(self):
        t = self.status.track_engine
        envs = sample_data()["envs"]
        # first pass is warm-up: it records state and stays quiet
        t(envs, {"web1": "ok"})
        self.assertEqual(self.sent, [])
        self.status._initialized[0] = True
        t(envs, {"web1": "down"})
        self.assertEqual(len(self.sent), 1)
        self.assertIn("engine is not answering", self.sent[0])
        t(envs, {"web1": "down"})           # no repeat while it stays down
        self.assertEqual(len(self.sent), 1)
        t(envs, {"web1": "ok"})             # recovery note
        self.assertEqual(len(self.sent), 2)
        self.assertIn("answers again", self.sent[1])

    def test_busy_does_not_alert_as_down(self):
        t = self.status.track_engine
        envs = sample_data()["envs"]
        t(envs, {"web1": "ok"})
        self.status._initialized[0] = True
        t(envs, {"web1": "busy"})
        self.assertEqual(self.sent, [])


class EnginePairTest(unittest.TestCase):
    """The pair guard. The portal must advertise CodeNomad's *declared* opencode
    dependency — never npm's `latest` opencode — because that is what keeps the
    pinned pair from drifting (a lone `npm i -g @opencode/cli@latest` kills the
    engine; see the 6.58 lesson)."""

    def setUp(self):
        self.status = load_status()

    def test_newer_version_compare(self):
        n = self.status._newer
        self.assertTrue(n("1.2.4", "1.2.3"))
        self.assertFalse(n("1.2.3", "1.2.4"))
        self.assertFalse(n("1.2.3", "1.2.3"))
        self.assertTrue(n("1.2.10", "1.2.9"))      # numeric, not lexicographic
        self.assertTrue(n("1.3.0", "1.2.99"))
        self.assertFalse(n("", "1.2.3"))           # nothing known -> never "newer"

    def _render_pair(self, current, target, mode="notify"):
        st = self.status
        old_mode, old_target = st.ENGINE_UPDATE, st._engine.get("target")
        try:
            st.ENGINE_UPDATE = mode
            st._engine["target"] = target
            statuses = {"web1": {"status": "online", "ms": 3,
                                 "engine_versions": {"codenomad": current[0],
                                                     "opencode": current[1]}}}
            return st.render(sample_data(), statuses, 0)
        finally:
            st.ENGINE_UPDATE, st._engine["target"] = old_mode, old_target

    def test_no_badge_when_the_fleet_is_on_the_target(self):
        html = self._render_pair(("1.2.3", "2.0.0"), ("1.2.3", "2.0.0"))
        self.assertNotIn('class="upd"', html)

    def test_badge_when_a_newer_pair_is_available(self):
        html = self._render_pair(("1.2.3", "2.0.0"), ("1.2.4", "2.0.1"))
        self.assertIn('class="upd"', html)          # a quiet marker on the node…
        self.assertIn('1.2.4 / 2.0.1', html)        # …naming the target pair
        self.assertIn('class="updbar"', html)       # and ONE fleet-level action

    def test_badge_when_only_opencode_is_newer(self):
        html = self._render_pair(("1.2.3", "2.0.0"), ("1.2.3", "2.0.9"))
        self.assertIn('1.2.3 / 2.0.9', html)
        self.assertIn('class="updbar"', html)

    def test_no_badge_when_the_target_is_unknown(self):
        # npm unreachable -> engine_target() is None: stay quiet, never nag
        html = self._render_pair(("1.2.3", "2.0.0"), None)
        self.assertNotIn('class="upd"', html)

    def test_no_badge_when_updates_are_off(self):
        html = self._render_pair(("1.2.3", "2.0.0"), ("1.2.4", "2.0.1"), mode="off")
        self.assertNotIn('<button class="upd"', html)

    def test_engine_target_takes_codenomads_declared_client(self):
        st = self.status
        payload = {"version": "9.9.9", "dependencies": {"@opencode/client": "^4.5.6"}}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, *a):
                return json.dumps(payload).encode()

        with mock.patch.object(st.urllib.request, "urlopen", lambda *a, **k: _Resp()):
            self.assertEqual(st.engine_target(), ("9.9.9", "4.5.6"))

    def test_engine_target_is_none_when_the_registry_is_unreachable(self):
        st = self.status

        def boom(*a, **k):
            raise OSError("no network")

        with mock.patch.object(st.urllib.request, "urlopen", boom):
            self.assertIsNone(st.engine_target())


class DashboardAttentionTest(unittest.TestCase):
    """The dashboard answers one question first: is anything wrong? Counts, then
    problems first inside each place."""

    def setUp(self):
        self.status = load_status()

    @staticmethod
    def _env(name, location="DC1"):
        return {"name": name, "aliases": [], "hosts": [name], "ip": "100.64.0.10",
                "port": 9898, "label": name.upper(), "location": location, "tags": []}

    def test_summary_counts_and_problems_first(self):
        data = {"domain": "example.com",
                "envs": [self._env("a-ok"), self._env("b-down"), self._env("c-off")]}
        statuses = {
            "a-ok": {"status": "online", "ms": 3, "cpu": 5, "mem": 20,
                     "engine_versions": {"codenomad": "1.0.0", "opencode": "2.0.0"}},
            "b-down": {"status": "online", "ms": 4, "cpu": 5, "mem": 20, "engine": "down",
                       "engine_versions": {"codenomad": "1.0.0", "opencode": "2.0.0"}},
            "c-off": {"status": "offline", "ms": 0},
        }
        html = self.status.render(data, statuses, 0)
        self.assertIn('id="s-total">3<', html)
        self.assertIn('id="s-online">2<', html)
        self.assertIn('id="s-offline">1<', html)
        self.assertIn('id="s-engdown">1<', html)
        order = [html.index(f'data-name="{n}"') for n in ("c-off", "b-down", "a-ok")]
        self.assertEqual(order, sorted(order))

    def test_zero_problem_counters_stay_hidden(self):
        data = {"domain": "example.com", "envs": [self._env("a-ok")]}
        html = self.status.render(data, {"a-ok": {"status": "online", "ms": 3}}, 0)
        self.assertIn('data-s="offline" title="показать только недоступные" hidden>', html)
        self.assertIn('data-s="total"', html)
        self.assertNotIn('class="gcnt"', html)          # nothing needs attention

    def test_update_bar_offers_one_fleet_action(self):
        st = self.status
        old = st._engine.get("target")
        data = {"domain": "example.com", "envs": [self._env("a-ok")]}
        current = {"status": "online", "ms": 3,
                   "engine_versions": {"codenomad": "1.0.0", "opencode": "2.0.0"}}
        try:
            st._engine["target"] = ("1.0.1", "2.0.1")
            html = st.render(data, {"a-ok": current}, 0)
            self.assertIn('class="updbar"', html)
            self.assertIn('data-engup="1.0.1|2.0.1"', html)
            st._engine["target"] = ("1.0.0", "2.0.0")
            html = st.render(data, {"a-ok": current}, 0)
            self.assertNotIn('class="updbar"', html)
        finally:
            st._engine["target"] = old

    def test_update_counter_follows_the_pair(self):
        st = self.status
        old = st._engine.get("target")
        data = {"domain": "example.com", "envs": [self._env("a-ok")]}
        statuses = {"a-ok": {"status": "online", "ms": 3,
                             "engine_versions": {"codenomad": "1.0.0", "opencode": "2.0.0"}}}
        try:
            st._engine["target"] = ("1.0.1", "2.0.1")   # fleet is one step behind
            html = st.render(data, statuses, 0)
            self.assertIn('id="s-update">1<', html)
            st._engine["target"] = ("1.0.0", "2.0.0")   # fleet is current
            html = st.render(data, statuses, 0)
            self.assertIn('data-s="update" title="доступна пара новее" hidden>', html)
        finally:
            st._engine["target"] = old


class DashboardViewTest(unittest.TestCase):
    """Tiles for a small fleet, a list for a big one; the person can override."""

    def setUp(self):
        self.status = load_status()

    @staticmethod
    def _env(name):
        return {"name": name, "aliases": [], "hosts": [name], "ip": "100.64.0.10",
                "port": 9898, "label": name.upper(), "location": "DC1", "tags": ["linux"]}

    def _data(self, n):
        return {"domain": "example.com", "envs": [self._env(f"n{i}") for i in range(n)]}

    def test_small_fleet_opens_as_tiles(self):
        html = self.status.render(self._data(3), {}, 0)
        self.assertIn('class="card node"', html)
        self.assertNotIn('class="nrow node"', html)

    def test_big_fleet_opens_as_a_list(self):
        html = self.status.render(self._data(9), {}, 0)
        self.assertIn('class="nrow node"', html)
        self.assertNotIn('class="card node"', html)
        self.assertIn('id="st-n0"', html)       # same hooks as the card view

    def test_explicit_view_wins(self):
        self.assertIn('class="nrow node"', self.status.render(self._data(3), {}, 0, view="list"))
        self.assertIn('class="card node"', self.status.render(self._data(9), {}, 0, view="cards"))

    def test_bad_view_falls_back_to_auto(self):
        self.assertIn('class="card node"', self.status.render(self._data(3), {}, 0, view="bogus"))

    def test_rail_holds_places_and_view_switch(self):
        html = self.status.render(self._data(3), {}, 0)
        self.assertIn('class="rail"', html)
        self.assertIn('data-location="all"', html)
        self.assertIn('class="segbtn', html)
        self.assertIn('id="probtn"', html)

    def test_onboarding_has_no_rail(self):
        html = self.status.render({"domain": "example.com", "envs": []}, {}, 0)
        self.assertIn("shell lone", html)
        self.assertNotIn('class="rail"', html)

    def test_rows_carry_sort_data_and_controls(self):
        statuses = {"n0": {"status": "online", "ms": 3, "cpu": 12.5, "mem": 40}}
        html = self.status.render(self._data(3), statuses, 0, view="list")
        self.assertIn('data-ord="0"', html)
        self.assertIn('data-cpu="12.5"', html)
        self.assertIn('id="lhead"', html)          # sortable column header
        self.assertIn('data-sort="name"', html)
        self.assertIn('id="palet"', html)

    def test_header_belongs_to_the_list_view_only(self):
        html = self.status.render(self._data(3), {}, 0, view="cards")
        self.assertNotIn('id="lhead"', html)


if __name__ == "__main__":
    unittest.main()

