import json
from pathlib import Path

decks = []
for f in sorted(Path("decklists").glob("*.json")):
    decks.append(json.load(open(f)))

Path("app").mkdir(exist_ok=True)
with open("app/data.json", "w") as f:
    json.dump(decks, f)

print(f"Aggregated {len(decks)} decks -> app/data.json")
