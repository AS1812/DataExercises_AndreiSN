"""Configuration for the Tallgrass Interstate Gas Transmission (TIGT) scraper.

All site-specific values live here so the same code can target another pipeline
by changing PIPELINE_ID (the site is generic across its pipelines).
"""
from pathlib import Path

# --- Target site ----------------------------------------------------------
BASE = "https://pipeline.tallgrassenergylp.com"
PIPELINE_ID = 302          # 302 = Tallgrass Interstate Gas Transmission (TIGT)
POSTING_TYPE = "OA"        # OA = Operationally Available (the topic the task asks for)
POINT_URL = f"{BASE}/Pages/Point.aspx?pipeline={PIPELINE_ID}&type={POSTING_TYPE}"

# --- What to pull ----------------------------------------------------------
N_GAS_DAYS = 3             # "the last 3 gas days"

# Cycles are discovered live from the page's Cycle dropdown
# (scraper.discover_cycles); the scraper pulls every option EXCEPT those below,
# so "all cycles" adapts automatically if the site adds/removes one.
# "Best Available" is excluded: it is not a nomination cycle, it just returns
# the latest already-posted cycle. Verified empirically to be 100% redundant --
# every Best-Available row is reproduced by the real cycles (union coverage
# 100% across gas days and both directions; it equals Intra-Day 3 exactly).
EXCLUDE_CYCLES = {"Best Available"}

# Both flow directions. The Receipt/Delivery radio genuinely changes the data
# (verified: Receipt and Delivery return different row sets).
DIRECTIONS = ("Receipt", "Delivery")

# --- Selectors (captured from the live Point Capacity page) ----------------
SEL = {
    "gas_day":  "#mainContent_tbGasFlow",      # text field, format M/D/YYYY
    "gas_end":  "#mainContent_tbgasflowend",
    "cycle":    "#mainContent_ddlCycle",       # <select>, no autopostback
    "receipt":  "#mainContent_rbReceipt",
    "delivery": "#mainContent_rbDelivery",
    "retrieve": "#mainContent_btnRetrieve",
    "download": "#mainContent_btnDownload",
    "message":  "#mainContent_lmsg",
}

# --- Browser / anti-bot ----------------------------------------------------
# The site is behind Imperva/Incapsula: a plain HTTP client gets a JS challenge
# page, so we drive a real Chromium that executes the challenge. Central time
# matters because the gas day is defined in Central Clock Time.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
TIMEZONE = "America/Chicago"
HEADLESS = True

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw_downloads"          # exact site downloads, one per pull
OUT_DIR = ROOT / "outputs"                # standardized, upload-ready output
PER_CYCLE_DIR = OUT_DIR / "per_cycle"     # one standardized CSV per cycle+direction
MANIFEST = RAW_DIR / "manifest.json"
