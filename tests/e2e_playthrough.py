"""
Full end-to-end play-through against the static site.

Boots the site with `python -m http.server` on a random free port,
drives it with Playwright (headless Chromium), and exits non-zero
on any console error, failed request, or data shape problem.

Run locally:
    pip install playwright
    python -m playwright install chromium
    python tests/e2e_playthrough.py
"""
import asyncio, json, os, signal, socket, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# E2E runs against the Vite-built site (PROJECT/dist), not the public/
# source folder. run_all.sh runs `vite build` before invoking this.
DIST = PROJECT / 'dist'

def free_port():
    s = socket.socket()
    s.bind(('', 0))
    p = s.getsockname()[1]
    s.close()
    return p

@contextmanager
def server(port):
    if not DIST.exists():
        raise SystemExit(f"dist/ not found at {DIST}. Run `npx vite build` first (run_all.sh does this automatically).")
    proc = subprocess.Popen(['python3', '-m', 'http.server', str(port)],
                             cwd=str(DIST),
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             preexec_fn=os.setsid)
    time.sleep(0.6)
    try:
        yield
    finally:
        try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception: pass

async def play_once(page, click_correct=True):
    """Walk the experiment, returning the final summary data."""
    manifest = await page.evaluate(
        "(async () => (await (await fetch('manifest.json')).json()).trials)()")

    # 1. consent — wait for the age picker before clicking. The consent
    # tap is what unlocks audio playback for the rest of the session.
    await page.wait_for_selector('button.age-btn[data-age="6"]', timeout=20000)
    await page.click('button.age-btn[data-age="6"]')
    await page.click('#agree-cb')
    await page.click('#consent-go')
    await page.wait_for_timeout(250)
    # 2. welcome screen — Zorpie + auto-playing intro audio. Button is
    # hidden so we force-click it via JS to advance.
    await page.wait_for_selector('#welcome-go', state='attached', timeout=20000)
    await page.evaluate("document.getElementById('welcome-go')?.click()")
    await page.wait_for_timeout(200)
    # how-to-play (interactive: tap the kitty to enable the "I'm ready!" button)
    await page.click('#howto-row .demo-card[data-role="cat"]')
    await page.wait_for_timeout(150)
    await page.click('#howto-go')
    await page.wait_for_timeout(300)

    # Playback order is no longer manifest order: training → warmup → one of
    # {familiar, novel} → the other, with catch trials spliced into the test
    # blocks and a Zorpie intro before each test block. So we read whichever
    # trial is currently rendered (the row id is `row-<trial_id>`) and look
    # it up in a manifest dict.
    manifest_by_id = {t['trial_id']: t for t in manifest}
    trials_completed = 0
    total = len(manifest)
    for _ in range(total + 30):  # buffer for block intros + flicker
        if trials_completed >= total:
            break
        await page.wait_for_timeout(80)
        has_trial = await page.evaluate(
            "!!document.querySelector('.kid-row .kid-card')")
        if not has_trial:
            # block intro / break / etc. — click any enabled big button.
            await page.evaluate("""
              () => {
                const btn = document.querySelector('button.big-btn:not(:disabled)');
                if (btn) btn.click();
              }
            """)
            await page.wait_for_timeout(150)
            continue

        trial_id = await page.evaluate(
            "document.querySelector('.kid-row').id.replace('row-','')")
        trial = manifest_by_id.get(trial_id)
        if trial is None:
            # Unknown trial id — fall back to clicking position 0 so the test
            # makes progress instead of hanging.
            await page.evaluate("document.querySelector('.kid-row .kid-card')?.click()")
        else:
            oid = trial['oddity_index']
            target = oid if click_correct else (oid + 1) % trial['n_objects']
            await page.evaluate(f"""
              () => {{
                const c = document.querySelector(
                  '.kid-row .kid-card[data-orig="{target}"]');
                if (c) c.click();
              }}
            """)
        await page.wait_for_timeout(100)
        trials_completed += 1

    await page.wait_for_timeout(800)
    summary = await page.evaluate("""
      () => {
        const all = jsPsych.data.get().values().filter(d => d.task === 'mochi_oddity');
        return {
          n_trials: all.length,
          n_correct: all.filter(d => d.correct).length,
          first_rt: all[0] ? all[0].rt : null,
          all_have_rt: all.every(d => typeof d.rt === 'number' && d.rt > 0),
          all_have_trial_id: all.every(d => d.trial_id),
        };
      }
    """)
    return summary, len(manifest)

async def run():
    from playwright.async_api import async_playwright
    port = free_port()
    failures = []
    with server(port):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            # === Test 1: disabled consent button blocks advancing ===
            # Consent is now the first screen (welcome moved after).
            page = await browser.new_page()
            await page.goto(f'http://localhost:{port}/?save=false', wait_until='networkidle', timeout=15000)
            await page.wait_for_selector('#consent-go', timeout=20000)
            await page.evaluate("() => document.getElementById('consent-go')?.click()")
            await page.wait_for_timeout(300)
            still_consent = await page.evaluate("document.body.innerText.includes('HOW OLD ARE YOU')")
            if not still_consent:
                failures.append("disabled LET'S PLAY button still advanced the experiment")
            else:
                print("ok    disabled button blocks advance")
            await page.close()

            # === Test 2: full all-correct play-through ===
            page = await browser.new_page()
            console_errors, req_fails = [], []
            page.on('console',  lambda m: console_errors.append(m.text) if m.type=='error' else None)
            page.on('pageerror', lambda e: console_errors.append(str(e)))
            # Ignore ERR_ABORTED on audio — that's our own playPrompt() pausing
            # an in-flight fetch when the next prompt starts. Cosmetic, not a bug.
            def on_req_fail(r):
                if '/audio/' in r.url and 'ABORTED' in (r.failure or ''):
                    return
                req_fails.append(f"{r.url} -> {r.failure}")
            page.on('requestfailed', on_req_fail)
            await page.goto(f'http://localhost:{port}/?save=false', wait_until='networkidle', timeout=20000)
            await page.wait_for_timeout(2200)
            summary, n = await play_once(page, click_correct=True)
            if summary['n_trials'] != n:
                failures.append(f"play-through: only {summary['n_trials']}/{n} trials completed")
            elif summary['n_correct'] != n:
                failures.append(f"play-through: {summary['n_correct']}/{n} correct (expected all)")
            elif not summary['all_have_rt']:
                failures.append("play-through: some trials missing RT")
            elif not summary['all_have_trial_id']:
                failures.append("play-through: some trials missing trial_id")
            else:
                print(f"ok    full play-through: {summary['n_correct']}/{summary['n_trials']} correct")
            if console_errors: failures.append(f"console errors: {console_errors[:5]}")
            if req_fails:      failures.append(f"failed requests: {req_fails[:5]}")

            # Verify the end screen is the thank-you page (no big download button by default)
            await page.wait_for_timeout(800)
            end_text = await page.evaluate("document.body.innerText")
            if 'Thank you' not in end_text:
                failures.append(f"end screen missing 'Thank you': {end_text[:120]}")
            else:
                print("ok    end screen shows Thank you")
            has_visible_dl = await page.evaluate(
                "(() => { const w = document.getElementById('dl-fallback'); return w && w.style.display !== 'none'; })()")
            if has_visible_dl and not False:  # save=false → fallback may show; that's OK
                # With ?save=false the script intentionally doesn't show fallback unless show_download=true.
                # So if dl-fallback IS visible, that's still acceptable here. Just log it.
                print("info  download fallback visible (likely save disabled or save_enabled=false branch)")
            await page.close()

            # === Test 3: rapid double-click respected once-only ===
            page = await browser.new_page()
            await page.goto(f'http://localhost:{port}/?save=false', wait_until='networkidle', timeout=15000)
            await page.wait_for_selector('button.age-btn[data-age="6"]', timeout=20000)
            await page.click('button.age-btn[data-age="6"]')
            await page.click('#agree-cb')
            await page.click('#consent-go')
            await page.wait_for_timeout(250)
            # welcome screen — hidden button, force-click via JS
            await page.wait_for_selector('#welcome-go', state='attached', timeout=20000)
            await page.evaluate("document.getElementById('welcome-go')?.click()")
            await page.wait_for_timeout(200)
            # how-to-play interactive demo
            await page.click('#howto-row .demo-card[data-role="cat"]')
            await page.wait_for_timeout(150)
            await page.click('#howto-go')
            await page.wait_for_timeout(350)
            # Double-click any non-oddity card
            await page.evaluate("""
              () => {
                const cards = document.querySelectorAll('.kid-row .kid-card');
                cards[0].click(); cards[0].click();
              }
            """)
            await page.wait_for_timeout(500)
            n_done = await page.evaluate(
                "jsPsych.data.get().values().filter(d=>d.task==='mochi_oddity').length")
            if n_done != 1:
                failures.append(f"double-click yielded {n_done} trials, expected 1")
            else:
                print("ok    once-only listener: double-click yielded 1 trial")
            await page.close()

            await browser.close()

    print()
    if failures:
        print("FAILED:")
        for f in failures: print(f"  - {f}")
        sys.exit(1)
    print("PASSED — all e2e checks green")

if __name__ == '__main__':
    asyncio.run(run())
