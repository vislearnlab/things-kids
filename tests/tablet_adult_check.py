"""Drive the adult/Prolific flow on tablet viewports with real touch events.

Checks the things that only break on a touch device or at tablet aspect
ratios, and that a CSS read-through cannot confirm:

  1. The consent checkbox is actually on screen and tappable (it was
     previously below the fold of a nested scroller).
  2. Taps — not mouse clicks — register on the trial cards.
  3. The response lockout genuinely rejects an early tap AND the card still
     works afterwards. The old { once: true } handler would have consumed
     the listener on the ignored tap and left the card dead forever.
  4. Nothing overflows horizontally, in portrait or landscape.

Run against a dev server:  npm run dev
    python3 tests/tablet_adult_check.py
"""

import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000/"
PROLIFIC = "?PROLIFIC_PID=tablet_test&STUDY_ID=s&SESSION_ID=x&study=deploy_smoke_test&save=false"

# Landscape first: that is how the museum kiosk runs. Portrait still matters
# for the adult/Prolific version, where participants use their own devices.
DEVICES = [
    ("iPad landscape", 1180, 820),
    ("iPad mini landscape", 1133, 744),
    ("iPad Pro landscape", 1366, 1024),
    ("iPad portrait", 820, 1180),
]

fails, notes = [], []


def check(cond, label):
    (notes if cond else fails).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label)


def run(pw, name, w, h):
    print(f"\n=== {name} ({w}x{h}) ===")
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": w, "height": h},
                         device_scale_factor=2, is_mobile=True,
                         has_touch=True)
    pg = ctx.new_page()
    pg.goto(BASE + PROLIFIC, wait_until="networkidle")
    pg.wait_for_timeout(1200)

    # 1. Consent checkbox visible within the viewport, without scrolling.
    cb = pg.locator("#ca-cb")
    check(cb.count() == 1, "adult consent screen shown")
    if cb.count():
        box = cb.bounding_box()
        on_screen = box and box["y"] >= 0 and (box["y"] + box["height"]) <= h
        check(bool(on_screen), f"checkbox within viewport (y={box['y']:.0f} h={h})")
        check(box["width"] >= 24, f"checkbox tap target >= 24px (got {box['width']:.0f})")
        cb.tap()
        check(cb.is_checked(), "checkbox toggles on tap")
        go = pg.locator("#consent-go")
        check(not go.is_disabled(), "continue enabled after agreeing")
        go.tap()

    # No horizontal overflow anywhere in the flow.
    ow = pg.evaluate("document.documentElement.scrollWidth")
    check(ow <= w + 1, f"no horizontal overflow ({ow} <= {w})")

    # 2. Instructions screen, then into the task.
    pg.wait_for_timeout(600)
    if pg.locator("text=Please turn your audio on").count():
        check(True, "adult instructions shown")
        pg.locator(".big-btn").first.tap()
    pg.wait_for_timeout(9000)  # welcome audio auto-advance + how-to-play

    # How-to-play gates its button behind tapping the odd demo card, so tap
    # that first wherever it appears. wait_for_selector (not a fixed sleep)
    # so we catch the trial the moment it renders — a blanket wait would let
    # the 400ms lockout expire before we could observe it.
    for _ in range(8):
        if pg.locator(".kid-card").count():
            break
        demo = pg.locator(".demo-card.diff")
        if demo.count():
            demo.first.tap()
            pg.wait_for_timeout(300)
        btn = pg.locator(".big-btn:visible:not([disabled])")
        if btn.count():
            btn.first.tap()
        try:
            pg.wait_for_selector(".kid-card", timeout=1500)
            break
        except Exception:
            pass

    cards = pg.locator(".kid-card")
    check(cards.count() == 3, f"trial shows 3 cards (got {cards.count()})")
    if cards.count() == 3:
        cb0 = cards.first.bounding_box()
        check(cb0["width"] >= 100, f"card tap target {cb0['width']:.0f}px wide")

        # 3. Lockout. Tap immediately: nothing should register. Then wait it
        # out and tap the SAME card: it must still work. Under the old
        # { once: true } handler the ignored tap consumed the listener and
        # left the card permanently dead — that is the regression this guards.
        # Count recorded oddity responses rather than looking for a .correct
        # class: a registered tap advances the trial almost immediately, so
        # the class is gone before it can be observed. jsPsych's data store
        # is the durable record of whether the response actually counted.
        def responses():
            return pg.evaluate(
                "window.jsPsych.data.get().filter({task:'things_oddity'}).count()")

        before = responses()
        check(pg.locator(".kid-row.locked").count() > 0, "row starts locked")
        cards.first.tap(force=True)
        pg.wait_for_timeout(60)
        check(responses() == before, "early tap does not register during lockout")

        pg.wait_for_timeout(700)
        check(pg.locator(".kid-row.locked").count() == 0, "lockout releases")
        pg.locator(".kid-card").first.tap()
        pg.wait_for_timeout(500)
        check(responses() == before + 1,
              "tap registers after lockout (card not killed by the ignored tap)")

    ow2 = pg.evaluate("document.documentElement.scrollWidth")
    check(ow2 <= w + 1, f"no horizontal overflow in task ({ow2} <= {w})")

    pg.screenshot(path=f"tests/_shot_{name.replace(' ', '_')}.png")
    ctx.close(); br.close()


with sync_playwright() as pw:
    for name, w, h in DEVICES:
        try:
            run(pw, name, w, h)
        except Exception as e:
            fails.append(f"{name}: {type(e).__name__} {e}")
            print(f"  ERROR {e}")

print(f"\n{len(notes)} passed, {len(fails)} failed")
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if fails else 0)
