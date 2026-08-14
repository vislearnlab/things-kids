"""Assert a finished session stays marked complete.

The regression this guards shipped live and cost the `complete` flag on
every Prolific adult who finished: data is saved after every trial, and the
last-gasp `pagehide` beacon sent an *in-progress* payload. On the kiosk that
beacon only ever fires on a real abandonment, but an adult who finishes is
redirected to Prolific — so the beacon fired right after the final save and
overwrote it, leaving complete:false and finishedAt:null on a session that
was in fact done. The trials survived (writes are cumulative); the flag that
analysis filters on did not.

Reproduces the exact production ordering: finish the timeline, let the final
save land, let the page navigate to the Prolific completion URL, then check
what the LAST write to arrive actually said.

Run:  npx vite build && python3 tests/save_completion_check.py
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

# Deliberately a dumb last-write-wins sink, mirroring an unguarded Mongo
# upsert. The point is to catch a bad payload leaving the browser, not to
# re-test the server-side guard in src/mongo.ts.
received: list = []
lock = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        try:
            payload = json.loads(body).get("data", {})
        except Exception:
            payload = {"_unparseable": True}
        with lock:
            received.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *_args):
        pass


def free_port():
    s = socket.socket()
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def advance_to_trials(pg):
    """Adult consent -> instructions -> how-to-play -> first real trial."""
    pg.wait_for_selector("#ca-cb", timeout=20000)
    pg.click("#ca-cb")
    pg.click("#consent-go")
    # Welcome screen auto-advances on audio; how-to-play gates its button
    # behind tapping the odd demo card. Poll rather than sleep blindly.
    for _ in range(40):
        if pg.locator(".kid-card").count():
            return True
        demo = pg.locator(".demo-card.diff")
        if demo.count():
            demo.first.click()
            pg.wait_for_timeout(150)
        btn = pg.locator(".big-btn:visible:not([disabled])")
        if btn.count():
            btn.first.click()
        pg.wait_for_timeout(400)
    return False


def n_responses(pg):
    return pg.evaluate(
        "window.jsPsych.data.get().filter({task:'things_oddity'}).count()")


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

# "__" prefix marks a probe session; analysis/fetch_data.py filters those out.
URL = (f"http://127.0.0.1:{port}/?PROLIFIC_PID=__save_completion_check"
       f"&STUDY_ID=s&SESSION_ID=x&study=deploy_smoke_test&lockout_ms=0")

with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page()
    # The completion redirect is the whole point — it is what fires pagehide.
    # Serve it locally instead of hitting Prolific for real.
    pg.route("**app.prolific.com/**",
             lambda route: route.fulfill(status=200, content_type="text/html",
                                         body="<html>prolific stub</html>"))
    pg.goto(URL, wait_until="networkidle")

    check(advance_to_trials(pg), "reached the first trial")

    # A few trials is enough: the bug is in what happens at the end, and
    # every trial writes the same in-progress shape.
    for _ in range(3):
        pg.wait_for_selector(".kid-card", timeout=15000)
        before = n_responses(pg)
        pg.locator(".kid-card").first.click()
        for _ in range(30):
            pg.wait_for_timeout(100)
            if n_responses(pg) > before:
                break

    done_trials = n_responses(pg)
    check(done_trials >= 3, f"recorded {done_trials} trials before finishing")

    with lock:
        mid = list(received)
    check(len(mid) >= done_trials,
          f"saved after every trial ({len(mid)} writes for {done_trials} trials)")
    check(all(p.get("complete") is False for p in mid),
          "in-progress writes are marked complete:false")

    # End the timeline early — same code path as running out of trials.
    pg.evaluate("window.jsPsych.abortExperiment()")

    # Final save, then the armed redirect to Prolific (2.5s after it lands),
    # then pagehide. Give the whole sequence room to play out.
    pg.wait_for_timeout(6000)

    with lock:
        all_writes = list(received)

    check(any(p.get("complete") is True for p in all_writes),
          "a complete:true write was sent at all")

    last = all_writes[-1] if all_writes else {}
    check(last.get("complete") is True,
          f"LAST write to arrive is complete:true (got {last.get('complete')!r})")
    check(bool(last.get("finishedAt")),
          f"LAST write carries finishedAt (got {last.get('finishedAt')!r})")
    check(last.get("n_trials") == done_trials,
          f"LAST write keeps all {done_trials} trials (got {last.get('n_trials')})")

    br.close()

httpd.shutdown()

print(f"\n{len(fails)} failed")
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if fails else 0)
