# udo-dash

A local, read-only browser dashboard for udo time tracking:
week, month and day-strip views of your sessions, plus what's due next.

Needs Python 3.9+ and `udo` on `PATH`. Nothing to install.

```sh
python3 udo_dash.py            # http://localhost:8765/, opens the browser
python3 udo_dash.py --port 9000 --no-open
```

It only runs read-only `udo` commands and only listens on `127.0.0.1`. `UDO_ROOT` is
respected.

## Tests

```sh
python3 -m unittest discover -s tests
node --test tests/test_logic.mjs
```

Node is only needed for the page logic tests.

Design: `docs/superpowers/specs/2026-11-03-udo-dash-design.md`.
