# MTG Decklist Scraper — Design Spec
_Date: 2026-05-05_

## Overview

Scrape all decklists from the NA PM Champs '26: Premodern Unchained event (spicerack.gg event ID `2921762`). Each player was allowed to "unchain" one banned card. The goal is to collect structured deck data for downstream analysis: which banned cards were played, win rates by unchained card, archetype detection, etc.

---

## Project Layout

```
/
├── banned_cards.json          # static list of premodern banned cards
├── decklists/                 # output directory, one JSON per deck
│   ├── 001_bryson_bonham.json
│   ├── 002_ryan_sala-bankston.json
│   └── ...
└── scrape.py                  # the scraper script
```

---

## Data Sources

**Spicerack event page:**
`https://www.spicerack.gg/events/decklists?event_id=2921762`

The page renders server-side HTML (no JS required). Contains a table with:
- `place` — final standing (integer; some entries have no place assigned)
- `spicerack_archetype` — label from spicerack ("Archetype missing" or "Other" for most entries)
- `pilot` — player name
- `moxfield_url` — link to the deck on moxfield.com

**Moxfield public API:**
`https://api2.moxfield.com/v2/decks/all/<publicId>`

Returns structured JSON with mainboard and sideboard card data. The `publicId` is extracted from the moxfield URL path.

**Record (W/L/D):** Not available on the decklists page. Will attempt to find it on the event standings page (`https://www.spicerack.gg/events/2921762`). If unavailable, the `record` field is stored as `null`.

---

## Banned Cards List

Stored in `banned_cards.json` as a JSON array of strings. The 28 banned cards for Premodern:

```json
[
  "Amulet of Quoz", "Balance", "Brainstorm", "Bronze Tablet", "Channel",
  "Demonic Consultation", "Earthcraft", "Entomb", "Flash", "Force of Will",
  "Goblin Recruiter", "Grim Monolith", "Jeweled Bird", "Land Tax",
  "Mana Vault", "Memory Jar", "Mind Twist", "Mind's Desire",
  "Mystical Tutor", "Necropotence", "Rebirth", "Strip Mine",
  "Tempest Efreet", "Tendrils of Agony", "Timmerian Fiends",
  "Tolarian Academy", "Vampiric Tutor", "Windfall"
]
```

---

## Output JSON Schema (per deck)

Filename: `{place:03d}_{pilot_slug}.json` (e.g. `001_bryson_bonham.json`).
Entries without a place number use prefix `000`.

```json
{
  "event_id": "2921762",
  "event_name": "NA PM Champs '26: Premodern Unchained hosted by the Rochester Royals",
  "place": 1,
  "pilot": "Bryson Bonham",
  "spicerack_archetype": "Archetype missing",
  "moxfield_url": "https://www.moxfield.com/decks/vfSB1tKNBEiSgkZ9Zwzdiw",
  "record": null,
  "unchained_card": "Necropotence",
  "mainboard": [
    {"count": 4, "name": "Dark Ritual"},
    {"count": 1, "name": "Necropotence"}
  ],
  "sideboard": [
    {"count": 2, "name": "Coffin Purge"}
  ]
}
```

**`unchained_card` detection:** Cross-reference all mainboard card names against `banned_cards.json`. Exactly one match is expected per deck. If zero or multiple banned cards are found, the field is set to `null` and a warning is printed.

---

## Scraper Behavior (`scrape.py`)

1. Load `banned_cards.json` into a set.
2. Fetch the spicerack event decklists page with `requests`. Parse HTML with `BeautifulSoup`. Extract the standings table rows: place, archetype, pilot, moxfield URL.
3. Attempt to fetch the event standings page to get W/L/D records; build a dict keyed by pilot name. If unavailable, skip gracefully.
4. For each deck entry:
   a. Extract the Moxfield `publicId` from the URL.
   b. GET `https://api2.moxfield.com/v2/decks/all/<publicId>`.
   c. Parse mainboard and sideboard card counts and names.
   d. Detect `unchained_card` from mainboard ∩ banned set.
   e. Assemble the output JSON object.
   f. Write to `decklists/{place}_{pilot_slug}.json`.
   g. Sleep 0.5s between Moxfield API calls.
5. Print a summary: total decks processed, any warnings (missing unchained card, multiple banned cards found, API errors).

---

## Dependencies

- Python 3.x (stdlib: `json`, `time`, `re`, `pathlib`)
- `requests`
- `beautifulsoup4`

No virtual environment required beyond `pip install requests beautifulsoup4`.

---

## Future Work (out of scope for this scrape)

- Archetype detection from card composition
- Win rate analysis by unchained card
- Meta share analysis
- Record (W/L/D) enrichment if standings data becomes available
