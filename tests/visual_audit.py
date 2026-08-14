"""Visual audit at iPad-Pro-landscape and phone dimensions.

Drives the experiment through key screens, snapshots each viewport, and
reports overflow / layout issues. Doesn't replace real device testing —
just catches obvious "this widget won't fit" problems before deploying.

Run from repo root:
    python3 tests/visual_audit.py
"""
import asyncio, os, signal, socket, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / "dist"
OUT = PROJECT / "tests" / "_audit"
OUT.mkdir(exist_ok=True)


def free_port():
    s = socket.socket()
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@contextmanager
def server(port):
    if not DIST.exists():
        raise SystemExit(f"dist/ not found at {DIST}. Run `npx vite build` first.")
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", str(port)],
        cwd=str(DIST),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    time.sleep(0.6)
    try:
        yield
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass


# Viewport presets we care about (CSS pixels, not physical).
VIEWPORTS = {
    "desktop_1440":          (1440, 900),
    "ipad_pro_12_landscape": (1366, 1024),
    "ipad_pro_11_landscape": (1194, 834),
    "ipad_pro_12_portrait":  (1024, 1366),
    "iphone_14_portrait":     (393, 852),
    "iphone_14_landscape":    (852, 393),
}


async def shoot(page, name, screen):
    path = OUT / f"{screen}__{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    return path


async def overflow_check(page):
    """Returns (overflow_x, overflow_y, scroll_w, scroll_h, vw, vh)."""
    return await page.evaluate(
        """() => {
          const d = document.documentElement;
          const b = document.body;
          return {
            overflow_x: d.scrollWidth  > d.clientWidth + 1,
            overflow_y: d.scrollHeight > d.clientHeight + 1,
            scroll_w: d.scrollWidth,  scroll_h: d.scrollHeight,
            vw: d.clientWidth,        vh: d.clientHeight,
          };
        }"""
    )


async def audit(p, screen, port, w, h):
    print(f"\n=== {screen}  {w}x{h} ===")
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=f"/tmp/_pw_audit_{screen}",
        viewport={"width": w, "height": h},
        device_scale_factor=2,
        is_mobile=("phone" in screen or "iphone" in screen),
        has_touch=True,
        headless=True,
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    issues = []

    async def step(name, action=None):
        if action:
            await action()
        await page.wait_for_timeout(250)
        info = await overflow_check(page)
        path = await shoot(page, name, screen)
        flag = []
        if info["overflow_x"]:
            flag.append(f"horiz overflow ({info['scroll_w']} > {info['vw']})")
        if info["overflow_y"]:
            flag.append(f"vert overflow ({info['scroll_h']} > {info['vh']})")
        msg = "ok" if not flag else "WARN " + "; ".join(flag)
        print(f"  {name:20s} -> {msg}  [{path.name}]")
        if flag:
            issues.append((screen, name, flag))

    await page.goto(f"http://localhost:{port}/?save=false", wait_until="networkidle")
    await page.wait_for_selector("#consent-go", state="attached", timeout=15000)
    await step("01_consent")

    await page.click('button.age-btn[data-age="6"]')
    await page.click("#agree-cb")
    await page.wait_for_timeout(150)
    await step("02_consent_filled")

    await page.click("#consent-go")
    await page.wait_for_selector("#welcome-go", state="attached", timeout=15000)
    await step("03_welcome")

    await page.evaluate("document.getElementById('welcome-go')?.click()")
    await page.wait_for_selector("#howto-row", timeout=15000)
    await step("04_how_to_play")

    await page.click('#howto-row .demo-card[data-role="cat"]')
    await page.wait_for_timeout(200)
    await step("05_how_to_play_correct")

    await page.click("#howto-go")
    await page.wait_for_selector(".kid-row .kid-card", timeout=15000)
    await step("06_first_trial")

    # Click correct on a few trials so we can see a block intro after warmup.
    for _ in range(14):
        info = await page.evaluate(
            """async () => {
              const row = document.querySelector('.kid-row');
              if (!row) return null;
              return row.id.replace('row-','');
            }"""
        )
        if not info:
            break
        manifest = await page.evaluate(
            "(async () => (await (await fetch('manifest.json')).json()).trials)()"
        )
        target = next((t["oddity_index"] for t in manifest if t["trial_id"] == info), 0)
        await page.evaluate(
            f"document.querySelector('.kid-row .kid-card[data-orig=\"{target}\"]')?.click()"
        )
        await page.wait_for_timeout(120)

    # Most likely on a block intro now (after warmup).
    await page.wait_for_timeout(400)
    has_intro = await page.evaluate(
        "!!document.querySelector('button.big-btn[id^=\"block-go\"]')"
    )
    if has_intro:
        await step("07_block_intro")

    await ctx.close()
    return issues


async def main():
    from playwright.async_api import async_playwright

    port = free_port()
    all_issues = []
    with server(port):
        async with async_playwright() as p:
            for name, (w, h) in VIEWPORTS.items():
                all_issues += await audit(p, name, port, w, h)
    print()
    if all_issues:
        print(f"=== FOUND {len(all_issues)} layout warnings ===")
        for screen, step, flags in all_issues:
            print(f"  [{screen}] {step}: {', '.join(flags)}")
    else:
        print("=== no overflow issues across all viewports ===")
    print(f"\nscreenshots: {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
