import argparse
import json
import os
import re
import sys
from typing import Dict, Optional

import requests
from playwright.sync_api import Locator, Page, sync_playwright

SOURCE_URL = "https://29029.co/products/steamboat-2026"
MONDAY_API = "https://api.monday.com/v2"
PARTICIPANTS = [
    "Ty Brookover",
    "Carey Cooper",
    "Barbee Fagan",
    "Jared King",
    "Jill King",
    "Jessica Seidel",
]


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def load_config():
    path = os.getenv("CONFIG_PATH", "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def first_visible(locator: Locator) -> Optional[Locator]:
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                return item
        except Exception:
            pass
    return None


def _scroll_full_page(page: Page):
    """Scroll progressively so lazy-loaded embeds near the bottom are initialized."""
    try:
        height = page.evaluate("document.body.scrollHeight")
        y = 0
        while y < height:
            page.evaluate("window.scrollTo(0, arguments[0])", y)
            page.wait_for_timeout(350)
            y += 900
            height = page.evaluate("document.body.scrollHeight")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1800)
    except Exception:
        pass


def _candidate_searches(ctx):
    return [
        ctx.get_by_role("searchbox"),
        ctx.locator('input[type="search"]'),
        ctx.locator('input[placeholder*="search" i]'),
        ctx.locator('input[aria-label*="search" i]'),
        ctx.locator('input[placeholder*="participant" i]'),
        ctx.locator('input[aria-label*="participant" i]'),
        ctx.locator('input[placeholder*="name" i]'),
    ]


def find_ascent_search(page: Page) -> Locator:
    """Find the participant search input on the page or inside an embedded frame."""
    # Scroll the entire page first because the board is near the bottom and may lazy-load.
    _scroll_full_page(page)

    # Try the main page plus every iframe. Playwright Frame exposes the same locator APIs.
    contexts = [page] + list(page.frames)
    seen = set()
    for ctx in contexts:
        key = getattr(ctx, "url", "") or str(id(ctx))
        if key in seen:
            continue
        seen.add(key)

        for locator in _candidate_searches(ctx):
            try:
                count = locator.count()
            except Exception:
                continue
            for i in range(count):
                item = locator.nth(i)
                try:
                    if item.is_visible():
                        return item
                except Exception:
                    continue

    # Last-resort diagnostic: print frames and visible inputs to the Actions log.
    print("DIAGNOSTIC: search input not found. Frames:", file=sys.stderr)
    for i, frame in enumerate(page.frames):
        try:
            print(f"  frame[{i}] url={frame.url}", file=sys.stderr)
            inputs = frame.locator("input")
            for j in range(min(inputs.count(), 20)):
                inp = inputs.nth(j)
                try:
                    print(
                        "    input", j,
                        "type=", inp.get_attribute("type"),
                        "placeholder=", inp.get_attribute("placeholder"),
                        "aria-label=", inp.get_attribute("aria-label"),
                        "visible=", inp.is_visible(),
                        file=sys.stderr,
                    )
                except Exception:
                    pass
        except Exception:
            pass

    raise RuntimeError("Could not find the Ascent Board participant search input")

def extract_lap(text: str, name: str) -> Optional[int]:
    t = re.sub(r"\s+", " ", text or " ")
    patterns = [
        r"\b(?:lap|laps|ascent|ascents|hike|hikes)\s*(?:completed)?\s*[:#-]?\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s*(?:lap|laps|ascent|ascents|hike|hikes)\b",
        r"\bcompleted\s*[:#-]?\s*(\d{1,2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.I)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 20:
                return n

    # Conservative fallback: only use a small number close to the matching name.
    pos = t.casefold().find(name.casefold())
    around = t[max(0, pos - 100): pos + 260] if pos >= 0 else t[:360]
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", around)]
    nums = [n for n in nums if 0 <= n <= 20]
    return nums[-1] if nums else None


def read_filtered_result(page: Page, name: str, search: Locator) -> Optional[int]:
    """Type a participant name into the board search and read that result's lap count."""
    search.fill("")
    search.fill(name)
    page.wait_for_timeout(1300)

    # First preference: a visible result container that includes the exact participant name.
    name_loc = page.get_by_text(name, exact=True)
    for i in range(name_loc.count()):
        el = name_loc.nth(i)
        try:
            if not el.is_visible():
                continue
        except Exception:
            continue

        # Walk upward through row/card ancestors. Stop before grabbing huge page sections.
        target = el
        for _ in range(8):
            try:
                txt = target.inner_text(timeout=2500)
            except Exception:
                txt = ""
            if txt and len(txt) <= 1800 and normalize(name) in normalize(txt):
                lap = extract_lap(txt, name)
                if lap is not None:
                    return lap
            target = target.locator("xpath=..")

    # Second preference: after filtering, inspect visible text in the board/search vicinity.
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
        idx = body_text.casefold().find(name.casefold())
        if idx >= 0:
            snippet = body_text[max(0, idx - 180): idx + 520]
            lap = extract_lap(snippet, name)
            if lap is not None:
                return lap
    except Exception:
        pass

    return None


def scrape_laps(debug_dir: Optional[str] = None) -> Dict[str, int]:
    """Use the Ascent Board's own search box to look up each participant."""
    results: Dict[str, int] = {}
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1400})
        page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(8000)

        try:
            search = find_ascent_search(page)
        except Exception:
            if debug_dir:
                page.screenshot(path=os.path.join(debug_dir, "search_not_found.png"), full_page=True)
                try:
                    with open(os.path.join(debug_dir, "page.html"), "w", encoding="utf-8") as f:
                        f.write(page.content())
                except Exception:
                    pass
            raise
        try:
            search.scroll_into_view_if_needed()
        except Exception:
            pass

        for name in PARTICIPANTS:
            lap = read_filtered_result(page, name, search)
            if lap is not None:
                results[name] = lap
                print(f"{name}: {lap}")
            else:
                print(f"WARNING: could not identify lap for {name}", file=sys.stderr)

            if debug_dir:
                safe = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
                page.screenshot(path=os.path.join(debug_dir, f"{safe}.png"), full_page=True)

        search.fill("")
        browser.close()

    return results


def monday_graphql(token: str, query: str, variables: dict):
    r = requests.post(
        MONDAY_API,
        headers={"Authorization": token, "Content-Type": "application/json"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def get_board_items(token: str, board_id: int):
    q = """
    query ($board: [ID!]) {
      boards(ids: $board) {
        items_page(limit: 500) { items { id name } }
      }
    }
    """
    data = monday_graphql(token, q, {"board": [str(board_id)]})
    return data["boards"][0]["items_page"]["items"]


def update_lap(token: str, board_id: int, item_id: str, column_id: str, lap: int):
    q = """
    mutation ($board: ID!, $item: ID!, $column: String!, $value: JSON!) {
      change_column_value(board_id: $board, item_id: $item, column_id: $column, value: $value) { id }
    }
    """
    value = json.dumps(str(lap))
    monday_graphql(token, q, {
        "board": str(board_id), "item": str(item_id), "column": column_id, "value": value
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scrape-only", action="store_true", help="Read and print lap counts; do not touch Monday")
    parser.add_argument("--debug-dir", help="Optional directory for one screenshot per participant lookup")
    args = parser.parse_args()

    laps = scrape_laps(debug_dir=args.debug_dir)
    print("\nCurrent lap counts (last-name order):")
    for name in PARTICIPANTS:
        print(f"- {name}: {laps.get(name, 'NOT FOUND')}")

    if args.scrape_only:
        if not laps:
            raise SystemExit("No participant laps found.")
        return

    cfg = load_config()
    token = os.environ.get("MONDAY_API_TOKEN")
    if not token:
        raise SystemExit("MONDAY_API_TOKEN is required unless --scrape-only is used")

    board_id = int(cfg["monday_board_id"])
    column_id = cfg["lap_completed_column_id"]
    name_overrides = {normalize(k): v for k, v in cfg.get("name_overrides", {}).items()}

    if not laps:
        raise SystemExit("No participant laps found; refusing to update Monday.")

    items = get_board_items(token, board_id)
    by_name = {normalize(i["name"]): i for i in items}

    for source_name in PARTICIPANTS:
        if source_name not in laps:
            continue
        lap = laps[source_name]
        target_name = name_overrides.get(normalize(source_name), source_name)
        item = by_name.get(normalize(target_name))
        if not item:
            print(f"WARNING: Monday item not found for {target_name}; skipped", file=sys.stderr)
            continue
        update_lap(token, board_id, item["id"], column_id, lap)
        print(f"Updated {target_name}: Lap Completed = {lap}")


if __name__ == "__main__":
    main()
