import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import udo_dash  # noqa: E402

TREE = {
    "rows": [
        {"path": "Uni", "name": "Uni", "depth": 0, "kind": "workspace"},
        {"path": "Uni/lab 3", "name": "lab 3", "depth": 1, "status": "to do"},
        {"path": "-x", "name": "-x", "depth": 0, "status": "to do"},
    ]
}

FAKE_UDO = """#!{python}
import json, os, sys
with open(os.environ["FAKE_UDO_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_UDO_FAIL"):
    sys.stderr.write("error: database is locked\\n")
    sys.exit(1)
if sys.argv[1] == "ls":
    print(json.dumps({tree}))
else:
    print(json.dumps({{"rows": [], "cmd": sys.argv[1]}}))
"""


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        directory = Path(self.tmp.name)
        fake = directory / "udo"
        fake.write_text(FAKE_UDO.format(python=sys.executable, tree=repr(TREE)))
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = directory / "log"
        self.log.touch()

        saved = {k: os.environ.get(k) for k in ("PATH", "FAKE_UDO_LOG", "FAKE_UDO_FAIL")}

        def restore():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)
        os.environ["PATH"] = str(directory)
        os.environ["FAKE_UDO_LOG"] = str(self.log)
        os.environ.pop("FAKE_UDO_FAIL", None)

        self.server = udo_dash.make_server(0)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, host=None, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(connection.close)
        headers = {"Host": host} if host else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()

    def get_json(self, path, **kwargs):
        status, body = self.request(path, **kwargs)
        return status, json.loads(body)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_sessions_runs_exact_args(self):
        status, _ = self.get_json("/api/sessions?from=2026-10-26&to=2026-11-02")
        self.assertEqual(status, 200)
        self.assertEqual(
            self.calls(),
            [
                [
                    "session", "list", "/",
                    "--from", "2026-10-26 00:00",
                    "--to", "2026-11-02 00:00",
                    "--json",
                ]
            ],
        )

    def test_tree_args(self):
        status, body = self.get_json("/api/tree")
        self.assertEqual(status, 200)
        self.assertEqual(body, TREE)
        self.assertEqual(self.calls(), [["ls", "/", "-t", "--json"]])

    def test_node_args(self):
        status, _ = self.get_json("/api/node?path=" + quote("Uni/lab 3"))
        self.assertEqual(status, 200)
        self.assertEqual(self.calls()[-1], ["show", "--json", "--", "Uni/lab 3"])

    def test_task_sessions_args(self):
        status, _ = self.get_json("/api/task-sessions?path=" + quote("Uni/lab 3"))
        self.assertEqual(status, 200)
        self.assertEqual(
            self.calls()[-1], ["session", "list", "--all", "--json", "--", "Uni/lab 3"]
        )

    def test_dash_name_stays_a_path(self):
        status, _ = self.get_json("/api/node?path=-x")
        self.assertEqual(status, 200)
        self.assertEqual(self.calls()[-1], ["show", "--json", "--", "-x"])

    def test_unknown_path_rejected(self):
        for route in ("node", "task-sessions"):
            status, body = self.get_json(f"/api/{route}?path=--deleted")
            self.assertEqual(status, 400)
            self.assertIn("error", body)
        self.assertEqual({call[0] for call in self.calls()}, {"ls"})

    def test_missing_path_rejected(self):
        status, _ = self.get_json("/api/node")
        self.assertEqual(status, 400)
        self.assertEqual(self.calls(), [])

    def test_bad_dates_rejected(self):
        for query in (
            "from=2026-13-01&to=2026-11-02",
            "from=tomorrow&to=2026-11-02",
            "from=2026-10-26",
            "to=2026-10-26",
            "from=2026-11-02&to=2026-11-02",
            "from=2026-11-03&to=2026-11-02",
            "from=2026-1-1&to=2026-1-2",
        ):
            status, _ = self.get_json("/api/sessions?" + query)
            self.assertEqual(status, 400, query)
        self.assertEqual(self.calls(), [])

    def test_range_cap(self):
        status, _ = self.get_json("/api/sessions?from=2026-07-26&to=2026-11-03")
        self.assertEqual(status, 200)
        status, body = self.get_json("/api/sessions?from=2026-07-25&to=2026-11-03")
        self.assertEqual(status, 400)
        self.assertIn("100", body["error"])

    def test_bad_host_rejected(self):
        status, _ = self.get_json("/api/tree", host="evil.example")
        self.assertEqual(status, 403)
        status, _ = self.get_json("/api/tree", host=f"evil.example:{self.port}")
        self.assertEqual(status, 403)
        self.assertEqual(self.calls(), [])
        for host in (f"localhost:{self.port}", f"127.0.0.1:{self.port}"):
            status, _ = self.get_json("/api/tree", host=host)
            self.assertEqual(status, 200, host)

    def test_udo_failure_reports_stderr(self):
        os.environ["FAKE_UDO_FAIL"] = "1"
        status, body = self.get_json("/api/tree")
        self.assertEqual(status, 502)
        self.assertIn("database is locked", body["error"])

    def test_udo_missing(self):
        os.environ["PATH"] = str(Path(self.tmp.name) / "nowhere")
        status, body = self.get_json("/api/tree")
        self.assertEqual(status, 502)
        self.assertIn("udo", body["error"])

    def test_unknown_route_404(self):
        status, _ = self.request("/api/nope")
        self.assertEqual(status, 404)
        status, _ = self.request("/udo_dash.py")
        self.assertEqual(status, 404)

    def test_post_rejected(self):
        status, _ = self.request("/api/tree", method="POST")
        self.assertEqual(status, 405)
        self.assertEqual(self.calls(), [])

    def test_page_served(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<script id=\"logic\">", body)


if __name__ == "__main__":
    unittest.main()
