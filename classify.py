"""
Classify each deck in decklists/ into a named archetype.
Updates the `archetype` field in each JSON file in place.
"""
import json
from pathlib import Path

GOBLIN_CARDS = {
    'Goblin Lackey', 'Goblin Warchief', 'Goblin Matron', 'Goblin Ringleader',
    'Goblin Recruiter', 'Goblin Piledriver', 'Siege-Gang Commander',
    'Goblin Sharpshooter', 'Gempalm Incinerator', 'Skirk Prospector',
    'Goblin King', 'Goblin Tinkerer', 'Goblin Pyromancer',
}

REANIMATION_CARDS = {'Reanimate', 'Exhume', 'Animate Dead', 'Necromancy', 'Life // Death'}

RITUAL_CARDS = {'Dark Ritual', 'Cabal Ritual'}

# Manual overrides: pilot name -> archetype (applied after rule-based classification)
OVERRIDES = {
    'Bryson Bonham': 'Rogue',
}

ELF_CARDS = {
    'Llanowar Elves', 'Fyndhorn Elves', 'Elvish Spirit Guide', 'Priest of Titania',
    'Wirewood Symbiote', 'Wirewood Hivemaster', 'Wellwisher', 'Heritage Druid',
}


def classify(deck: dict) -> str:
    cards = {c['name'] for c in deck['mainboard']}

    # ── Specific combo/prison archetypes ─────────────────────────────────────

    if 'Stasis' in cards and 'Forsaken City' in cards:
        return 'Stasis'

    if 'Argothian Enchantress' in cards:
        return 'Enchantress'

    if 'Earthcraft' in cards:
        return 'Earthcraft'

    if sum(1 for g in GOBLIN_CARDS if g in cards) >= 3:
        return 'Goblins'

    # Reanimator: Entomb + reanimation spell, or Buried Alive + reanimation
    if 'Entomb' in cards and REANIMATION_CARDS & cards:
        return 'Reanimator'
    if 'Buried Alive' in cards and REANIMATION_CARDS & cards:
        return 'Reanimator'

    if 'Replenish' in cards:
        return 'Replenish'

    if 'Donate' in cards and 'Illusions of Grandeur' in cards:
        return 'Donate'

    if "Yawgmoth's Bargain" in cards:
        return 'Bargain'

    if 'Academy Rector' in cards and 'Show and Tell' in cards:
        return 'Rector Bargain'

    # Storm: any storm finisher + rituals or blue acceleration
    STORM_FINISHERS = {'Tendrils of Agony', "Mind's Desire", 'Brain Freeze'}
    BLUE_STORM_ACCEL = {'Cloud of Faeries', 'Snap', 'Frantic Search', 'Sapphire Medallion'}
    if STORM_FINISHERS & cards and (RITUAL_CARDS & cards or BLUE_STORM_ACCEL & cards):
        return 'Storm'
    if 'Burning Wish' in cards and RITUAL_CARDS & cards and "Lion's Eye Diamond" in cards:
        return 'Storm'

    if 'Oath of Druids' in cards:
        return 'Oath'

    if "Volrath's Shapeshifter" in cards:
        return 'HFEB' if 'Hermit Druid' in cards else 'FEB'

    if 'Survival of the Fittest' in cards:
        return 'Survival'

    if 'Pox' in cards:
        return 'Pox'

    if 'Bottomless Pit' in cards and 'The Rack' in cards:
        return 'Pit Rack'

    if 'Standstill' in cards and "Mishra's Factory" in cards:
        return 'Landstill'

    # ── Threshold: Nimble Mongoose or Werebear + cantrips ───────────────────

    if 'Nimble Mongoose' in cards or ('Werebear' in cards and 'Wild Mongrel' in cards):
        return 'Threshold'

    # ── Elves ────────────────────────────────────────────────────────────────

    if 'Priest of Titania' in cards and sum(1 for e in ELF_CARDS if e in cards) >= 3:
        return 'Elves'

    # ── Creature/tempo archetypes ─────────────────────────────────────────────

    if 'Phyrexian Dreadnought' in cards and ('Stifle' in cards or 'Vision Charm' in cards):
        return 'Dreadnought'

    if 'Quirion Dryad' in cards:
        return 'Gro'

    if 'Psychatog' in cards:
        return 'Psychatog'

    # ── Artifact archetypes ──────────────────────────────────────────────────

    if 'Tinker' in cards:
        return 'Tinker'

    if 'Smokestack' in cards and ('Sphere of Resistance' in cards or 'Tangle Wire' in cards):
        return 'Stax'

    # Winter Orb + mana artifact prison (no Smokestack)
    if 'Winter Orb' in cards and ('Karn, Silver Golem' in cards or 'Cursed Scroll' in cards) and 'Ancient Tomb' in cards:
        return 'Stax'

    # ── Black archetypes ──────────────────────────────────────────────────────

    if 'Necropotence' in cards:
        return 'Necro'

    if 'Hatred' in cards:
        return 'Suicide Black'

    # ── Red aggro ─────────────────────────────────────────────────────────────

    if 'Jackal Pup' in cards or ('Mogg Fanatic' in cards and 'Fireblast' in cards):
        return 'Sligh'

    # ── Generic black aggro-control ───────────────────────────────────────────

    if 'Hypnotic Specter' in cards and 'Dark Ritual' in cards:
        return 'MBC'

    return 'Rogue'


def main():
    counts: dict[str, int] = {}
    for f in sorted(Path('decklists').glob('*.json')):
        d = json.load(open(f))
        archetype = OVERRIDES.get(d['pilot'], classify(d))
        d['archetype'] = archetype
        with open(f, 'w') as fh:
            json.dump(d, fh, indent=2)
        counts[archetype] = counts.get(archetype, 0) + 1

    print('Archetype distribution:')
    for arch, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f'  {n:3d}  {arch}')
    print(f'\nTotal: {sum(counts.values())} decks')


if __name__ == '__main__':
    main()
