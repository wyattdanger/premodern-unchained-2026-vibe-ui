import json
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

EVENT_ID = "2921762"
EVENT_NAME = "NA PM Champs '26: Premodern Unchained hosted by the Rochester Royals"
DECKLISTS_URL = f"https://www.spicerack.gg/events/decklists?event_id={EVENT_ID}"
SWISS_STANDINGS_URL = f"https://api.spicerack.gg/api/magic-events/{EVENT_ID}/standings_for_round/?round_id=14169"
FINAL_STANDINGS_URL = f"https://api.spicerack.gg/api/magic-events/{EVENT_ID}/standings_for_round/?round_id=14178"
MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/{}"
OUTPUT_DIR = Path("decklists")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_banned_cards() -> set:
    try:
        with open("banned_cards.json") as f:
            return set(json.load(f))
    except FileNotFoundError:
        import sys
        sys.exit("ERROR: banned_cards.json not found. Run from the project root directory.")


def fetch_decklists_table(page) -> list[dict]:
    """Navigate to the spicerack decklists page with Playwright and extract table rows."""
    page.goto(DECKLISTS_URL, timeout=30000)
    page.wait_for_selector("table tbody tr", timeout=15000)

    rows = page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        return rows.map(row => {
            const cells = Array.from(row.querySelectorAll('td, th'));
            if (cells.length < 4) return null;
            const linkEl = cells[3].querySelector('a');
            return {
                place_text: cells[0].innerText.trim(),
                archetype: cells[1].innerText.trim(),
                pilot: cells[2].innerText.trim(),
                moxfield_url: linkEl ? linkEl.href : ''
            };
        }).filter(r => r !== null && r.moxfield_url !== '');
    }""")

    entries = []
    unranked_index = 0
    for row in rows:
        place_text = row['place_text']
        if place_text.isdigit():
            place = int(place_text)
            filename_prefix = f"{place:03d}_{slug(row['pilot'])}"
        else:
            unranked_index += 1
            place = None
            filename_prefix = f"000_{unranked_index:02d}_{slug(row['pilot'])}"

        entries.append({
            "place": place,
            "pilot": row['pilot'],
            "spicerack_archetype": row['archetype'],
            "moxfield_url": row['moxfield_url'],
            "filename": filename_prefix + ".json",
        })

    return entries


def fetch_standings(url: str, label: str) -> dict:
    """Returns dict mapping pilot name -> record string (e.g. '6-1-0')."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {s["name"]: s["record"] for s in data.get("standings", [])}
    except Exception as e:
        print(f"WARNING: Could not fetch {label} standings: {e}")
        return {}


def fetch_moxfield_deck(page, public_id: str) -> dict | None:
    """Navigate to the Moxfield deck page and capture the v3 API response."""
    try:
        with page.expect_response(
            lambda r: f"/v3/decks/all/{public_id}" in r.url and r.status == 200,
            timeout=15000,
        ) as response_info:
            page.goto(f"https://moxfield.com/decks/{public_id}", timeout=30000)
        return response_info.value.json()
    except Exception as e:
        print(f"  WARNING: failed to fetch deck {public_id}: {e}")
        return None


def parse_board(cards_dict: dict) -> list[dict]:
    return [
        {"count": entry["quantity"], "name": entry["card"]["name"]}
        for entry in cards_dict.values()
        if entry.get("quantity", 0) > 0
    ]


def detect_unchained(mainboard: list[dict], banned: set) -> str | None:
    found = [card["name"] for card in mainboard if card["name"] in banned]
    if len(found) == 1:
        return found[0]
    if len(found) == 0:
        print("  WARNING: no banned card found in mainboard")
    else:
        print(f"  WARNING: multiple banned cards found: {found}")
    return None


def main():
    banned = load_banned_cards()
    print(f"Loaded {len(banned)} banned cards")

    swiss_standings = fetch_standings(SWISS_STANDINGS_URL, "swiss (round 7)")
    final_standings = fetch_standings(FINAL_STANDINGS_URL, "final (top 2)")
    print(f"Fetched swiss records for {len(swiss_standings)} players")
    print(f"Fetched final records for {len(final_standings)} players")

    OUTPUT_DIR.mkdir(exist_ok=True)

    warnings = []
    processed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # Step 1: load index from cache or scrape spicerack in one go
            index_path = Path("index.json")
            if index_path.exists():
                entries = json.load(open(index_path))
                print(f"Loaded {len(entries)} entries from index.json (skipping spicerack scrape)")
            else:
                entries = fetch_decklists_table(page)
                print(f"Found {len(entries)} deck entries on spicerack")
                with open(index_path, "w") as f:
                    json.dump([{
                        "place": e["place"], "pilot": e["pilot"],
                        "spicerack_archetype": e["spicerack_archetype"],
                        "moxfield_url": e["moxfield_url"], "filename": e["filename"],
                    } for e in entries], f, indent=2)
                print(f"Saved index to {index_path}")

            # Step 2: fetch each deck by navigating to its moxfield page
            for i, entry in enumerate(entries):
                pilot = entry["pilot"]
                moxfield_url = entry["moxfield_url"]
                print(f"[{i+1}/{len(entries)}] {pilot} — {moxfield_url}")

                # Extract publicId from URL like https://www.moxfield.com/decks/<publicId>
                match = re.search(r"/decks/([^/?#]+)", moxfield_url)
                if not match:
                    print(f"  WARNING: could not parse moxfield URL: {moxfield_url}")
                    warnings.append(f"Bad URL for {pilot}: {moxfield_url}")
                    continue

                public_id = match.group(1)
                deck_data = fetch_moxfield_deck(page, public_id)

                if deck_data is None:
                    print(f"  WARNING: failed to fetch deck for {pilot}")
                    warnings.append(f"Fetch failed for {pilot} ({public_id})")
                    continue

                mainboard = parse_board(deck_data.get("boards", {}).get("mainboard", {}).get("cards", {}))
                sideboard = parse_board(deck_data.get("boards", {}).get("sideboard", {}).get("cards", {}))
                unchained = detect_unchained(mainboard, banned)

                swiss_record = swiss_standings.get(pilot)
                final_record = final_standings.get(pilot)

                output = {
                    "event_id": EVENT_ID,
                    "event_name": EVENT_NAME,
                    "place": entry["place"],
                    "pilot": pilot,
                    "spicerack_archetype": entry["spicerack_archetype"],
                    "moxfield_url": moxfield_url,
                    "swiss_record": swiss_record,
                    "final_record": final_record,
                    "unchained_card": unchained,
                    "mainboard": mainboard,
                    "sideboard": sideboard,
                }

                out_path = OUTPUT_DIR / entry["filename"]
                with open(out_path, "w") as f:
                    json.dump(output, f, indent=2)

                processed += 1
                time.sleep(0.5)
        finally:
            browser.close()

    print(f"\nDone. {processed}/{len(entries)} decks saved to {OUTPUT_DIR}/")
    if warnings:
        print(f"\n{len(warnings)} warnings:")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
