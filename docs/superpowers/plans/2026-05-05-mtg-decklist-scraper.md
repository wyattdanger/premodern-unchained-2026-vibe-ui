# MTG Decklist Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape all decklists from spicerack event 2921762, enrich with Moxfield card data and final standings, and save one JSON file per deck to `decklists/`.

**Architecture:** A single Python script (`scrape.py`) fetches the spicerack decklists page via `requests`, fetches final standings from the spicerack standings API, then uses a Playwright browser session to call the Moxfield v3 API for each deck's card data (browser cookies required). Detected unchained card is cross-referenced against `banned_cards.json`.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, `playwright` (Chromium)

---

## Key API/Data Facts (discovered during research)

- **Spicerack decklists page:** `https://www.spicerack.gg/events/decklists?event_id=2921762` — server-side rendered HTML table, no auth needed
- **Spicerack swiss standings (end of round 7):** `https://api.spicerack.gg/api/magic-events/2921762/standings_for_round/?round_id=14169` — public JSON API, no auth needed; equal footing for all 120+ players
- **Spicerack final standings (Top 2 / end of event):** `https://api.spicerack.gg/api/magic-events/2921762/standings_for_round/?round_id=14178` — includes top 8 playoff rounds; only top 8 players have more than 7 rounds of data
- **Moxfield deck API:** `https://api2.moxfield.com/v3/decks/all/<publicId>` — returns 403 from plain HTTP; requires browser cookies. Use `page.evaluate(fetch(...))` from within a Playwright browser session.
- **Moxfield response shape:** `data.boards.mainboard.cards` and `data.boards.sideboard.cards` — each entry has `quantity` (int) and `card.name` (string)

---

## File Structure

```
/
├── banned_cards.json     # CREATE: list of 28 banned premodern cards
├── scrape.py             # CREATE: main scraper script
└── decklists/            # CREATED BY SCRIPT at runtime
    └── {place}_{slug}.json
```

---

## Task 1: Create `banned_cards.json`

**Files:**
- Create: `banned_cards.json`

- [ ] **Step 1: Write the file**

```json
[
  "Amulet of Quoz",
  "Balance",
  "Brainstorm",
  "Bronze Tablet",
  "Channel",
  "Demonic Consultation",
  "Earthcraft",
  "Entomb",
  "Flash",
  "Force of Will",
  "Goblin Recruiter",
  "Grim Monolith",
  "Jeweled Bird",
  "Land Tax",
  "Mana Vault",
  "Memory Jar",
  "Mind Twist",
  "Mind's Desire",
  "Mystical Tutor",
  "Necropotence",
  "Rebirth",
  "Strip Mine",
  "Tempest Efreet",
  "Tendrils of Agony",
  "Timmerian Fiends",
  "Tolarian Academy",
  "Vampiric Tutor",
  "Windfall"
]
```

- [ ] **Step 2: Verify**

```bash
python3 -c "import json; cards = json.load(open('banned_cards.json')); print(len(cards), 'banned cards'); print(cards[:3])"
```
Expected output: `28 banned cards` followed by the first 3 card names.

---

## Task 2: Install dependencies

**Files:** none

- [ ] **Step 1: Install Python packages**

```bash
pip install requests beautifulsoup4 playwright
```

- [ ] **Step 2: Install Playwright's Chromium browser**

```bash
python -m playwright install chromium
```

- [ ] **Step 3: Verify**

```bash
python3 -c "import requests, bs4, playwright; print('OK')"
```
Expected: `OK`

---

## Task 3: Create `scrape.py`

**Files:**
- Create: `scrape.py`

- [ ] **Step 1: Write the complete script**

```python
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
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
    with open("banned_cards.json") as f:
        return set(json.load(f))


def fetch_decklists_table() -> list[dict]:
    """Scrape the spicerack decklists page and return a list of entries."""
    resp = requests.get(DECKLISTS_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    entries = []
    unranked_index = 0

    for row in soup.select("table tbody tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 4:
            continue

        place_text = cells[0].get_text(strip=True)
        archetype = cells[1].get_text(strip=True)
        pilot = cells[2].get_text(strip=True)
        link_tag = cells[3].find("a")
        if not link_tag:
            continue
        moxfield_url = link_tag.get("href", "")

        if place_text.isdigit():
            place = int(place_text)
            filename_prefix = f"{place:03d}_{slug(pilot)}"
        else:
            unranked_index += 1
            place = None
            filename_prefix = f"000_{unranked_index:02d}_{slug(pilot)}"

        entries.append({
            "place": place,
            "pilot": pilot,
            "spicerack_archetype": archetype,
            "moxfield_url": moxfield_url,
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
    """Call the Moxfield v3 API from within the browser context to bypass 403."""
    try:
        result = page.evaluate(f"""async () => {{
            const resp = await fetch('https://api2.moxfield.com/v3/decks/all/{public_id}', {{
                headers: {{
                    'authorization': 'Bearer undefined',
                    'x-moxfield-version': '2026.05.02.1',
                    'accept': 'application/json, text/plain, */*'
                }}
            }});
            if (!resp.ok) return null;
            return await resp.json();
        }}""")
        return result
    except Exception as e:
        print(f"  WARNING: Moxfield API error for {public_id}: {e}")
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

    entries = fetch_decklists_table()
    print(f"Found {len(entries)} deck entries on spicerack")

    swiss_standings = fetch_standings(SWISS_STANDINGS_URL, "swiss (round 7)")
    final_standings = fetch_standings(FINAL_STANDINGS_URL, "final (top 2)")
    print(f"Fetched swiss records for {len(swiss_standings)} players")
    print(f"Fetched final records for {len(final_standings)} players")

    OUTPUT_DIR.mkdir(exist_ok=True)

    warnings = []
    processed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to moxfield.com once to establish session cookies
        print("Initializing Moxfield session...")
        page.goto("https://moxfield.com", timeout=30000)
        page.wait_for_timeout(2000)  # let cookies settle

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

        browser.close()

    print(f"\nDone. {processed}/{len(entries)} decks saved to {OUTPUT_DIR}/")
    if warnings:
        print(f"\n{len(warnings)} warnings:")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script is syntactically valid**

```bash
python3 -m py_compile scrape.py && echo "Syntax OK"
```
Expected: `Syntax OK`

---

## Task 4: Run a smoke test on 3 decks

Before running the full scrape, test with a quick spot-check to confirm everything works end to end.

- [ ] **Step 1: Create a quick test script**

```python
# test_one.py
import json, re, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Just test the first deck from the table
DECKLISTS_URL = "https://www.spicerack.gg/events/decklists?event_id=2921762"
resp = requests.get(DECKLISTS_URL, timeout=30)
soup = BeautifulSoup(resp.text, "html.parser")
rows = soup.select("table tbody tr")
row = rows[0]
cells = row.find_all(["td", "th"])
pilot = cells[2].get_text(strip=True)
moxfield_url = cells[3].find("a").get("href", "")
public_id = re.search(r"/decks/([^/?#]+)", moxfield_url).group(1)
print(f"Testing: {pilot} — {public_id}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://moxfield.com", timeout=30000)
    page.wait_for_timeout(2000)
    result = page.evaluate(f"""async () => {{
        const resp = await fetch('https://api2.moxfield.com/v3/decks/all/{public_id}', {{
            headers: {{'authorization': 'Bearer undefined', 'x-moxfield-version': '2026.05.02.1', 'accept': 'application/json'}}
        }});
        if (!resp.ok) return {{error: resp.status}};
        const d = await resp.json();
        const mb = Object.values(d.boards.mainboard.cards).map(c => ({{count: c.quantity, name: c.card.name}}));
        return {{mainboard_count: mb.length, sample: mb.slice(0,3)}};
    }}""")
    browser.close()

print("Result:", json.dumps(result, indent=2))
```

- [ ] **Step 2: Run the test**

```bash
python3 test_one.py
```

Expected: prints the pilot name and a JSON result with `mainboard_count` > 0 and 3 sample cards.

- [ ] **Step 3: Clean up test file**

```bash
rm test_one.py
```

---

## Task 5: Run the full scrape

- [ ] **Step 1: Run `scrape.py`**

```bash
python3 scrape.py
```

This will take several minutes (120+ decks × 0.5s delay). Expected output pattern:
```
Loaded 28 banned cards
Found 124 deck entries on spicerack
Fetched records for 141 players
Initializing Moxfield session...
[1/124] Bryson Bonham — https://www.moxfield.com/decks/vfSB1tKNBEiSgkZ9Zwzdiw
[2/124] Ryan Sala-Bankston — ...
...
Done. 124/124 decks saved to decklists/
```

- [ ] **Step 2: Verify output count**

```bash
ls decklists/ | wc -l
```

Expected: matches the number of entries found (should be ~120-125).

- [ ] **Step 3: Spot-check a deck file**

```bash
python3 -c "
import json
deck = json.load(open('decklists/001_bryson_bonham.json'))
print('Pilot:', deck['pilot'])
print('Place:', deck['place'])
print('Swiss record:', deck['swiss_record'])
print('Final record:', deck['final_record'])
print('Unchained:', deck['unchained_card'])
print('Mainboard cards:', len(deck['mainboard']))
print('Sideboard cards:', len(deck['sideboard']))
"
```

Expected: all fields populated, `unchained_card` is one of the 28 banned cards, mainboard has 60 cards total (when counts are summed).

- [ ] **Step 4: Check for missing unchained cards**

```bash
python3 -c "
import json
from pathlib import Path
missing = []
for f in sorted(Path('decklists').glob('*.json')):
    d = json.load(open(f))
    if d['unchained_card'] is None:
        missing.append(f'{d[\"pilot\"]} ({f.name})')
print(f'{len(missing)} decks with no unchained card detected:')
for m in missing:
    print(' -', m)
"
```

Review any missing entries — they may need manual inspection.

- [ ] **Step 5: Summarize unchained card distribution**

```bash
python3 -c "
import json
from pathlib import Path
from collections import Counter
counts = Counter()
for f in Path('decklists').glob('*.json'):
    d = json.load(open(f))
    counts[d['unchained_card'] or '(none)'] += 1
for card, n in counts.most_common():
    print(f'{n:3d}  {card}')
"
```

Review the distribution — expect to see a variety of banned cards across the 120+ decks.

---

## Task 6: Commit the results

- [ ] **Step 1: Initialize git repo if needed**

```bash
git init
```

- [ ] **Step 2: Create a `.gitignore`**

```
__pycache__/
*.pyc
.playwright-mcp/
```

- [ ] **Step 3: Stage and commit**

```bash
git add banned_cards.json scrape.py decklists/ .gitignore docs/
git commit -m "feat: initial decklist scrape for NA PM Champs 2026 Unchained"
```
