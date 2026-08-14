"""Assert an adult's debrief comment actually reaches the saved payload.

The first 16 Prolific adults all stored debrief_comment: null. That was not
16 people declining to comment — jsPsych v8 clears the display element
BEFORE a trial's on_finish callback runs, so the handler's
document.getElementById('debrief-comment') found null every time and saved
an empty string. A silent data loss that looks exactly like silence.

This drives the real adult timeline to the debrief screen, types a comment,
clicks Finish, and reads what the browser actually POSTs.

Run:  npx vite build && python3 tests/debrief_comment_check.py
"""

import json
import socket
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / "dist"
COMMENT = "the forklift one was confusing -- test comment 123"

received, lock = [], threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            with lock:
                received.append(json.loads(body).get("data", {}))
        except Exception:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *_):
        pass


def free_port():
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close()
    return p


fails = []


def check(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        fails.append(label)


if not DIST.exists():
    raise SystemExit(f"dist/ not found at {DIST}. Run `npx vite build` first.")

port = free_port()
httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(DIST)))
threading.Thread(target=httpd.serve_forever, daemon=True).start()

URL = (f"http://127.0.0.1:{port}/?PROLIFIC_PID=__debrief_check&STUDY_ID=s"
       f"&SESSION_ID=x&study=deploy_smoke_test&lockout_ms=0&end_redirect_ms=0")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page()
    pg.route("**app.prolific.com/**", lambda r: r.fulfill(
        status=200, content_type="text/html", body="<html>stub</html>"))
    pg.goto(URL, wait_until="networkidle", timeout=60000)

    pg.wait_for_selector("#ca-cb", timeout=30000)
    pg.click("#ca-cb")
    pg.click("#consent-go")

    n = lambda: pg.evaluate(
        "window.jsPsych.data.get().filter({task:'things_oddity'}).count()")

    # Walk the whole 71-trial timeline — the debrief only exists at the end,
    # and abortExperiment() would skip the very thing under test.
    seen = 0
    for _ in range(1200):
        if pg.locator("#debrief-comment").count():
            break
        if pg.locator(".kid-card").count():
            before = n()
            pg.locator(".kid-card").first.click()
            for _ in range(20):
                pg.wait_for_timeout(50)
                if n() > before:
                    break
            seen = n()
            continue
        demo = pg.locator(".demo-card.diff")
        if demo.count():
            demo.first.click()
            pg.wait_for_timeout(100)
        btn = pg.locator(".big-btn:visible:not([disabled])")
        if btn.count():
            btn.first.click()
        pg.wait_for_timeout(150)

    check(pg.locator("#debrief-comment").count() == 1,
          f"reached the debrief screen after {seen} trials")
    if pg.locator("#debrief-comment").count():
        pg.fill("#debrief-comment", COMMENT)
        pg.locator(".big-btn:visible").first.click()
        pg.wait_for_timeout(4000)

    br.close()

httpd.shutdown()

with lock:
    writes = list(received)
final = [w for w in writes if w.get("complete") is True]
check(bool(final), f"a completed payload was POSTed ({len(writes)} writes total)")
if final:
    got = final[-1].get("debrief_comment")
    check(got == COMMENT, f"debrief_comment survives to the payload (got {got!r})")

print(f"\n{len(fails)} failed")
sys.exit(1 if fails else 0)
