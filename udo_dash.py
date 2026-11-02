#!/usr/bin/env python3
"""Local, read-only dashboard for udo. Serves index.html and runs fixed udo queries."""

import argparse
import json
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
            self.respond(200, route(query), "application/json")
        except BadRequest as error:
            self.respond_error(400, str(error))
        except (UdoError, json.JSONDecodeError) as error:
            self.respond_error(502, str(error))

    def do_POST(self):
        self.respond_error(405, "read-only")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *_args):
        pass


def make_server(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args()
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
