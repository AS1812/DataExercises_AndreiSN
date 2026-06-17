"""Playwright scraper for TIGT Operationally Available -> Point Capacity.

Pulls the last N gas days x each nomination cycle x {Receipt, Delivery} using
the site's own Download button (tab-delimited PointCapacity.txt), and saves
each pull separately into raw_downloads/ with a manifest.

The site is behind Imperva/Incapsula, so a plain HTTP client gets a JS
challenge page. We drive a real Chromium, which executes the challenge and
carries the session cookies for every subsequent download.

Run:  .venv/bin/python test1_scraper/scraper.py
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

import config as C


def _blocked(html: str) -> bool:
    """True while we're still looking at the Incapsula JS-challenge stub instead
    of the real page. The stub is tiny (<5 KB) and carries the Incapsula marker;
    the real Point Capacity page is ~700 KB."""
    return ("_Incapsula_Resource" in html or "Request unsuccessful" in html) and len(html) < 5000


def _open_point_page(ctx) -> Page:
    """Open the Point Capacity page and wait until we're past the Incapsula
    challenge. The first request usually returns the challenge stub; the real
    browser runs its JavaScript, which earns the session cookies and reloads to
    the real content."""
    page = ctx.new_page()
    page.goto(C.POINT_URL, wait_until="domcontentloaded", timeout=60000)
    # The challenge resolves asynchronously (JS runs -> cookies set -> reload),
    # so poll a few times and stop as soon as real content shows up.
    for attempt in range(6):
        if not _blocked(page.content()):
            break
        print(f"  [incapsula] solving challenge (attempt {attempt})...")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass                                  # networkidle can time out; retry anyway
        time.sleep(3)
    page.wait_for_load_state("networkidle", timeout=20000)
    if _blocked(page.content()):                  # still stuck after retries -> give up loudly
        raise RuntimeError("could not get past Incapsula bot wall")
    return page


def discover_gas_days(page: Page, n: int) -> list[date]:
    """The site pre-fills the gas-day field with the current gas day (Central
    time). We trust the site rather than the local clock and walk back n days.
    """
    default = page.input_value(C.SEL["gas_day"]).strip()  # e.g. "6/16/2026"
    m, d, y = (int(x) for x in default.split("/"))
    latest = date(y, m, d)
    days = [latest - timedelta(days=i) for i in range(n)]
    print(f"  site current gas day = {latest:%m/%d/%Y}; pulling {n}: "
          + ", ".join(f"{x:%m/%d/%Y}" for x in days))
    return days


def discover_cycles(page: Page) -> list[tuple[str, str]]:
    """Read the Cycle dropdown live and return (label, site_cycle_id) for every
    option except the excluded ones (config.EXCLUDE_CYCLES). Discovering them at
    runtime means "all cycles" adapts automatically if the site changes, with no
    hardcoded cycle list to go stale.
    """
    opts = page.eval_on_selector_all(
        f'{C.SEL["cycle"]} option',
        "els => els.map(e => ({label: e.textContent.trim(), value: e.value}))")
    cycles = [(o["label"], o["value"]) for o in opts
              if o["label"] and o["label"] not in C.EXCLUDE_CYCLES]
    print("  cycles discovered: " + ", ".join(f"{l} (id={v})" for l, v in cycles))
    return cycles


def _fmt(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"   # M/D/YYYY, no leading zeros


def pull_one(page: Page, gas_day: date, cycle_label: str, direction: str) -> str:
    """Drive one ASP.NET WebForms query and return the downloaded file's text.

    None of the three controls auto-post-back, so we can set them all and then
    submit: the gas-day textbox, the cycle dropdown, and the Receipt/Delivery
    radio (the radio is the only thing that distinguishes the two directions).
    """
    page.fill(C.SEL["gas_day"], _fmt(gas_day))            # M/D/YYYY into the text field
    page.select_option(C.SEL["cycle"], label=cycle_label)
    page.check(C.SEL["receipt"] if direction == "Receipt" else C.SEL["delivery"])

    # Retrieve = a postback that loads the grid for the current selection.
    page.click(C.SEL["retrieve"])
    page.wait_for_load_state("networkidle", timeout=30000)

    # Download = a second postback that streams a tab-delimited PointCapacity.txt.
    # expect_download() wraps the click so it captures the browser download event.
    with page.expect_download(timeout=30000) as dl_info:
        page.click(C.SEL["download"])
    dl = dl_info.value
    return open(dl.path(), "r", encoding="utf-8", errors="replace").read()


def main() -> None:
    C.RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    with sync_playwright() as p:
        # Launch Chromium with mild anti-bot hardening so Incapsula serves the
        # real page: drop the "controlled by automation" flag, and present a
        # normal UA/viewport. timezone is pinned to Central because the gas day
        # is defined in Central time. accept_downloads lets us capture the file.
        browser = p.chromium.launch(
            headless=C.HEADLESS, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=C.USER_AGENT, viewport={"width": 1366, "height": 900},
            locale="en-US", timezone_id=C.TIMEZONE, accept_downloads=True)
        ctx.add_init_script(                          # hide the navigator.webdriver flag
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        print("[scraper] opening Point Capacity page ...")
        page = _open_point_page(ctx)
        gas_days = discover_gas_days(page, C.N_GAS_DAYS)   # latest 3, read from the page
        cycles = discover_cycles(page)                     # all dropdown cycles, live

        # One download per (gas day x cycle x direction); each saved separately.
        total = len(gas_days) * len(cycles) * len(C.DIRECTIONS)
        i = 0
        for gas_day in gas_days:
            for cycle_label, site_cycle_id in cycles:
                for direction in C.DIRECTIONS:
                    i += 1
                    tag = f"{gas_day:%Y-%m-%d} {cycle_label:<12} {direction:<8}"
                    try:
                        text = pull_one(page, gas_day, cycle_label, direction)
                    except Exception as e:           # one bad pull must not kill the run
                        # re-open the page (fresh WebForms state) and try once more
                        print(f"  [{i}/{total}] {tag}  ERROR: {e!r} -- retrying once")
                        page = _open_point_page(ctx)
                        try:
                            text = pull_one(page, gas_day, cycle_label, direction)
                        except Exception as e2:
                            print(f"  [{i}/{total}] {tag}  FAILED: {e2!r}")
                            continue                 # skip this pull, keep going

                    n_rows = max(text.count("\n") - 1, 0)   # line count minus the header row
                    # name the raw file by the site's own cycle id (the dropdown value)
                    fname = (f"{C.PIPELINE_ID}_{gas_day:%y%m%d}_{site_cycle_id}_"
                             f"{direction[0]}.txt")
                    (C.RAW_DIR / fname).write_text(text, encoding="utf-8")
                    flag = "  (no data posted)" if n_rows == 0 else ""
                    print(f"  [{i}/{total}] {tag}  rows={n_rows:<4} -> {fname}{flag}")

                    # manifest row -> the formatter reads this to know each pull's
                    # gas day / cycle / direction (direction isn't in the file itself)
                    manifest.append({
                        "gas_day": f"{gas_day:%Y-%m-%d}",
                        "cycle_label": cycle_label,
                        "site_cycle_id": site_cycle_id,
                        "direction": direction,
                        "raw_file": fname,
                        "n_rows": n_rows,
                    })

        ctx.close()
        browser.close()

    C.MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    got = sum(1 for m in manifest if m["n_rows"] > 0)
    print(f"\n[scraper] done: {len(manifest)} pulls ({got} with data). "
          f"manifest -> {C.MANIFEST.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
