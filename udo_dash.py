#!/usr/bin/env python3
"""Local, read-only dashboard for udo. Serves index.html and runs fixed udo queries."""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PAGE = Path(__file__).resolve().parent / "index.html"
DEFAULT_PORT = 8765
MAX_RANGE_DAYS = 100
UDO_TIMEOUT_SECONDS = 10
SERVICE_LABEL = "local.udo-dash"


class BadRequest(Exception):
    """The request itself is wrong (HTTP 400)."""


class UdoError(Exception):
    """udo could not answer (HTTP 502)."""


def run_udo(args):
    """Run udo with an argument list and return its stdout."""
    try:
        result = subprocess.run(
            ["udo", *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=UDO_TIMEOUT_SECONDS,
            cwd="/",
        )
    except FileNotFoundError:
        raise UdoError("udo was not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise UdoError(f"udo took longer than {UDO_TIMEOUT_SECONDS} seconds") from None
    except OSError as error:
        raise UdoError(f"could not run udo: {error}") from None
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise UdoError(f"udo failed: {detail}")
    return result.stdout


def parse_day(value, name):
    try:
        if len(value) != 10:
            raise ValueError
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise BadRequest(f"{name} must be a date like 2026-11-02") from None


def sessions(query):
    start = parse_day(query.get("from"), "from")
    end = parse_day(query.get("to"), "to")
    days = (end - start).days
    if days <= 0:
        raise BadRequest("to must be after from")
    if days > MAX_RANGE_DAYS:
        raise BadRequest(f"at most {MAX_RANGE_DAYS} days can be loaded")
    return run_udo(
        [
            "session", "list", "/",
            "--from", f"{query['from']} 00:00",
            "--to", f"{query['to']} 00:00",
            "--json",
        ]
    )


def tree(_query):
    return run_udo(["ls", "/", "-t", "--json"])


def status(_query):
    return run_udo(["status", "--json"])


def known_path(query):
    """The path parameter, if it names a node in the tree."""
    path = query.get("path")
    if not path:
        raise BadRequest("path is required")
    rows = json.loads(run_udo(["ls", "/", "--json"])).get("rows", [])
    if not any(row.get("path") == path for row in rows):
        raise BadRequest("unknown path")
    return path


def node(query):
    return run_udo(["show", "--json", "--", known_path(query)])


def task_sessions(query):
    return run_udo(["session", "list", "--all", "--json", "--", known_path(query)])


ROUTES = {
    "/api/sessions": sessions,
    "/api/tree": tree,
    "/api/status": status,
    "/api/node": node,
    "/api/task-sessions": task_sessions,
}


class Handler(BaseHTTPRequestHandler):
    def host_allowed(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def respond(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def respond_error(self, status, message):
        self.respond(status, json.dumps({"error": message}), "application/json")

    def do_GET(self):
        if not self.host_allowed():
            self.respond_error(403, "unexpected Host header")
            return
        url = urlsplit(self.path)
        if url.path == "/":
            self.respond(200, PAGE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            return
        route = ROUTES.get(url.path)
        if route is None:
            self.respond_error(404, "not found")
            return
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        try:
            body = route(query)
        except BadRequest as error:
            self.respond_error(400, str(error))
        except UdoError as error:
            self.respond_error(502, str(error))
        except Exception as error:  # udo's output wasn't what this version expects.
            self.respond_error(502, f"unexpected answer from udo: {error}")
        else:
            self.respond(200, body, "application/json")

    def do_POST(self):
        self.respond_error(405, "read-only")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *_args):
        pass


def make_server(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def service_plist(python, script, udo, port, udo_root, log):
    """The launchd job. launchd's own PATH doesn't include Homebrew, so it is set here."""
    env = {"PATH": f"{os.path.dirname(udo)}:/usr/bin:/bin"}
    if udo_root:
        env["UDO_ROOT"] = udo_root
    return {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [python, script, "--port", str(port), "--no-open"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "WorkingDirectory": "/",
        "EnvironmentVariables": env,
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


def service_path():
    return Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"


def launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def uninstall_service():
    launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")
    service_path().unlink(missing_ok=True)
    print("udo-dash no longer starts at login.")


def install_service(port):
    udo = shutil.which("udo")
    if not udo:
        sys.exit("udo was not found on PATH.")
    # The stable link, not sys.executable: that path changes with Python upgrades.
    python = shutil.which("python3") or sys.executable
    plist = service_plist(
        python=python,
        script=str(Path(__file__).resolve()),
        udo=udo,
        port=port,
        udo_root=os.environ.get("UDO_ROOT"),
        log=str(Path.home() / "Library" / "Logs" / "udo-dash.log"),
    )
    path = service_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")
    with path.open("wb") as file:
        plistlib.dump(plist, file)
    result = launchctl("bootstrap", f"gui/{os.getuid()}", str(path))
    if result.returncode != 0:
        sys.exit(f"launchctl failed: {result.stderr.strip()}")
    print(f"udo-dash starts at login, on http://localhost:{port}/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument("--install-service", action="store_true", help="start at login (macOS launchd)")
    parser.add_argument("--uninstall-service", action="store_true", help="stop starting at login")
    args = parser.parse_args()
    if args.install_service:
        install_service(args.port)
        return
    if args.uninstall_service:
        uninstall_service()
        return
    try:
        server = make_server(args.port)
    except OSError as error:
        sys.exit(f"could not listen on port {args.port}: {error}. Try --port.")
    url = f"http://localhost:{server.server_address[1]}/"
    print(f"udo-dash on {url} (Ctrl+C to stop)")
    if not args.no_open:
        threading.Timer(0.2, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
