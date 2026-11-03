# udo-dash

A local, read-only browser dashboard for udo time tracking:
week, month and day-strip views of your sessions, plus what's due next.

Created for **udo 0.5.0**. It depends on the JSON output of `udo`, so other versions
may need changes.

Needs Python 3.9+ and `udo` on `PATH`. Nothing to install.

```sh
python3 udo_dash.py            # http://localhost:8765/, opens the browser
python3 udo_dash.py --port 9000 --no-open
```

It only runs read-only `udo` commands and only listens on `127.0.0.1`. `UDO_ROOT` is
respected.

## Start at login (macOS)

```sh
python3 udo_dash.py --install-service     # now and at every login; add --port N to change it
python3 udo_dash.py --uninstall-service
```

This writes a launchd job to `~/Library/LaunchAgents/local.udo-dash.plist` that restarts
the server if it stops, so you can bookmark `http://localhost:8765/`. It remembers the
paths of this folder, `python3` and `udo`: run `--install-service` again if one of them
moves. Page changes appear on reload; after changing `udo_dash.py`, run it again to restart
the server. Logs go to `~/Library/Logs/udo-dash.log`.

## Tests

```sh
python3 -m unittest discover -s tests
node --test tests/test_logic.mjs
```

Node is only needed for the page logic tests.

Design: `docs/superpowers/specs/2026-11-03-udo-dash-design.md`.
