"""Build Gear Compass data from the OSRS Wiki.

Pulls every {{Recommended equipment}} table from the wiki's Bucket store,
groups the tables by piece of combat content (boss, raid, slayer task,
wilderness, minigame), and enriches every recommended item with GE id,
image, members/tradeable flags, attack speed and equip requirements.

Output matches the `GearData` contract in src/types.ts.

Usage:  python -I scripts/build_data.py [out_path]   (default public/data/gear.json)
Env:    GEAR_CACHE=<dir>  cache HTTP responses there (for development only)
        GEAR_DEBUG=1      print where wiki and osrsreboxed requirements disagree

Pure stdlib; see scripts/README.md for sources and caveats.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date

UA = "GearCompass data builder (github.com/gear-compass)"
API = "https://oldschool.runescape.wiki/api.php"
PRICES = "https://prices.runescape.wiki/api/v1/osrs/mapping"
REBOXED = ("https://raw.githubusercontent.com/0xNeffarion/osrsreboxed-db/master/"
           "docs/items-json-slot/items-%s.json")
REBOXED_SLOTS = ["2h", "ammo", "body", "cape", "feet", "hands", "head", "legs",
                 "neck", "ring", "shield", "weapon"]

SLOTS = ["head", "cape", "neck", "ammo", "weapon", "body", "shield",
         "legs", "hands", "feet", "ring", "special"]
SKILLS = ["attack", "strength", "defence", "ranged", "magic", "prayer",
          "hitpoints", "slayer"]
MAX_TIERS = 5

# --------------------------------------------------------------------------
# Content classification
# --------------------------------------------------------------------------
# Base pages (text before the first "/") that are not combat content.
EXCLUDE_GROUPS = {
    "skilling / non-combat activity": [
        # (Wintertodt, Tempoross, Zalcano, Gemstone Crab are in Category:Bosses)
        "Wintertodt", "Tempoross", "Zalcano", "Guardians of the Rift", "Forestry",
        "Blast Furnace", "Blast mine", "Volcanic Mine", "Shooting Stars",
        "Sorceress's Garden", "Gemstone Crab", "Abyss", "Fishing Trawler",
        "Trouble Brewing", "Hallowed Sepulchre", "Chompy bird hunting",
        "Golem crafting", "Boat combat", "Sandstone rocks", "Sulliuscep",
        "Gout tuber", "Tangleroot", "Chest (Rogues' Castle)",
        "Chaos Temple (church)", "Loop half of key (moon key)"],
    "training / account guide": [
        "Hunter training", "Slayer training", "Pay-to-play Prayer training",
        "Free-to-play Magic training", "Free-to-play Melee training",
        "Free-to-play Prayer training", "Free-to-play Ranged training",
        "Free-to-play Ironman guide", "Ultimate Ironman Guide", "One-defence pure"],
    "combat achievement / speed-trial": [
        "Fighting as Intended", "Fighting as Intended II", "Why Fletch?",
        "Down Do Specs", "Budget Cutter", "Morytania Only", "Chompington",
        "Duel of Mokhaiotl", "The Bane of Demons", "Fight Caves Speed-Runner"],
}
EXCLUDE = {page: why for why, pages in EXCLUDE_GROUPS.items() for page in pages}
EXCLUDE_PATTERNS = [re.compile(p, re.I) for p in (
    r"speed-(trialist|runner|chaser)", r"\btraining$", r"\bguide\b",
    r"^Free-to-play ", r"Combat Achievements")]

# Explicit categories, overriding wiki categories (base page -> category).
CATEGORY_OVERRIDES = {
    # wilderness bosses & content
    "Callisto": "wilderness", "Artio": "wilderness", "Venenatis": "wilderness",
    "Spindel": "wilderness", "Vet'ion": "wilderness", "Calvar'ion": "wilderness",
    "Chaos Elemental": "wilderness", "Chaos Fanatic": "wilderness",
    "Scorpia": "wilderness", "Crazy archaeologist": "wilderness",
    "Revenants": "wilderness", "Ecumenical key": "wilderness",
    # in Category:Wilderness but not wilderness content in practice
    "King Black Dragon": "boss", "Deranged archaeologist": "boss",
    # slayer monsters that are fought as slayer tasks
    "Green dragon": "slayer", "Lava dragon": "slayer", "Krystilia": "slayer",
    "Metal dragons": "slayer", "Fossil Island Wyverns": "slayer",
    "Tormented Demon": "slayer", "Demonic gorilla": "slayer",
    # minigames / challenge content
    "Fortis Colosseum": "minigame", "Inferno": "minigame",
    "TzHaar Fight Cave": "minigame", "Barrows": "minigame",
    "Moons of Peril": "minigame", "Nightmare Zone": "minigame",
    "Barbarian Assault": "minigame",
    # bosses not (yet) in Category:Bosses
    "Demonic Brutus": "boss", "Mad Angel": "boss",
}
# Pages that are the same content under another name (base page -> name).
ALIASES = {
    "Fossil Island Wyverns": "Fossil Island wyverns",
    "Aquanite": "Aquanites",
    "Krystilia": "Wilderness Slayer",
    "Ecumenical key": "Wilderness God Wars Dungeon",
}
WIKI_CATS = ["Category:Raids", "Category:Bosses", "Category:Slayer monsters",
             "Category:Wilderness"]

# --------------------------------------------------------------------------
# Requirement overrides: items newer than osrsreboxed (Jan 2025) or where the
# automatic sources are wrong. name -> {"reqs": {...}, "quests": [...]}
# Only keys given are overridden.
# --------------------------------------------------------------------------
OVERRIDES = {
    "Barrows gloves": {"reqs": {}, "quests": ["Recipe for Disaster"]},
    "Slayer helmet (i)": {"reqs": {"defence": 10}},
    "Slayer helmet": {"reqs": {"defence": 10}},
    "Black mask (i)": {"reqs": {}},
    "Toxic blowpipe": {"reqs": {"ranged": 75}},
    "Abyssal whip": {"reqs": {"attack": 70}},
    "Dragon defender": {"reqs": {"defence": 60}},
    "Dragon scimitar": {"quests": ["Monkey Madness I"]},
    "Dragon longsword": {"quests": ["Lost City"]},
    "Dragon dagger": {"quests": ["Lost City"]},
    "Dragon battleaxe": {"quests": ["Heroes' Quest"]},
    "Dragon mace": {"quests": ["Heroes' Quest"]},
    "Dragon halberd": {"quests": ["Regicide"]},
    "Rune platebody": {"quests": ["Dragon Slayer I"]},
    "Green d'hide body": {"quests": ["Dragon Slayer I"]},
    "Dragon platebody": {"quests": ["Dragon Slayer II"]},
    "Dragon kiteshield": {"quests": ["Dragon Slayer II"]},
    "Dragon sq shield": {"quests": ["Legends' Quest"]},
    "Iban's staff (u)": {"quests": ["Underground Pass"]},
    "Iban's staff": {"quests": ["Underground Pass"]},
    "Silverlight": {"quests": ["Demon Slayer"]},
    # RFD gloves: the lead mentions the Defence needed to *unlock* them
    "Rune gloves": {"reqs": {}, "quests": ["Recipe for Disaster"]},
    "Adamant gloves": {"reqs": {}, "quests": ["Recipe for Disaster"]},
    "Dragon gloves": {"reqs": {}, "quests": ["Recipe for Disaster"]},
    "Sunspear": {"reqs": {}, "quests": ["The Blood Moon Rises"]},
    "Tortugan shield": {"reqs": {}, "quests": ["Troubled Tortugans"]},
    "Ivandis flail": {"quests": ["A Taste of Hope"]},
    "Blisterwood flail": {"quests": ["Sins of the Father"]},
}

PLINK_RE = re.compile(r"\[\[File:([^|\]]+)\|link=([^|\]]+)\]\]")

# --------------------------------------------------------------------------
# Item sources
# --------------------------------------------------------------------------
MAX_SOURCES = 8
MAX_COMPONENT_SOURCES = 10     # recipe components with more sources are commodities
GENERIC_WORDS = {"amulet", "ring", "staff", "boots", "bow", "necklace", "bracelet", "cape",
                 "shield", "gloves", "helm", "body", "legs", "mystic", "imbued", "blessed",
                 "elite", "seeking", "ancient", "dragon", "rune", "the", "a"}
COMMODITY_RX = re.compile(r"\brunes?$|^coins$|ball of wool|\bbar$|^thread$|^chain$|^vial\b|"
                          r"weapon poison|string$|^feathers?$|mould$|^molten glass|"
                          r"\bnails$|^bowl|^jug|^bucket|^water\b|^flax$", re.I)
# Item -> the component that is its real bottleneck, where the recipe chain is
# too deep or ambiguous for the automatic choice.
KEY_COMPONENTS = {
    "Amulet of torture": "Zenyte shard", "Necklace of anguish": "Zenyte shard",
    "Tormented bracelet": "Zenyte shard", "Ring of suffering": "Zenyte shard",
    "Ring of suffering (i)": "Zenyte shard", "Amulet of fury": "Onyx",
    "Blade of Saeldor": "Enhanced crystal weapon seed",
    "Bow of Faerdhinen": "Enhanced crystal weapon seed",
    "Dragonfire shield": "Draconic visage", "Dragonfire ward": "Skeletal visage",
    "Ancient wyvern shield": "Wyvern visage", "Dragon sq shield": "Shield left half",
    "Bonecrusher necklace": "Hydra tail", "Neitiznot faceguard": "Basilisk jaw",
    "Saradomin's blessed sword": "Saradomin sword", "Arclight": "Ancient shard",
    "Darklight": "Silverlight", "Slayer's staff (e)": "Slayer's enchantment",
    "Hallowed flail": "Hallowed mark", "Mystic dust staff": "Dust battlestaff",
    "Keris partisan of amascut": "Jewel of Amascut",
    "Keris partisan of breaching": "Breach of the Scarab",
    "Hunters' sunlight crossbow": "Sunlight antelope antler",
    "Trident of the Swamp": "Magic fang",
    # several equally rare parts: union of their sources
    "Soulreaper axe": ["Leviathan's lure", "Siren's staff", "Executioner's axe head",
                       "Eye of the Duke"],
}
# Source name (drop page / "Dropped from" without #variant) -> Content.name,
# for bosses whose loot comes from a differently named page.
SOURCE_ALIASES = {
    "Unsired": "Abyssal Sire", "Respiratory system": "Abyssal Sire",
    "Dagannoth Rex": "Dagannoth Kings", "Dagannoth Prime": "Dagannoth Kings",
    "Dagannoth Supreme": "Dagannoth Kings",
    "Dusk": "Grotesque Guardians", "Dawn": "Grotesque Guardians",
    "Eldric the Ice King": "Royal Titans", "Branda the Fire Queen": "Royal Titans",
    "Ancient chest": "Chambers of Xeric", "Monumental chest": "Theatre of Blood",
    "Chest (Tombs of Amascut)": "Tombs of Amascut",
    "Chest (The Fractured Archive)": "The Fractured Archive",
    "Chest (Barrows)": "Barrows",
    "Rewards Chest (Fortis Colosseum)": "Fortis Colosseum",
    "Lunar Chest": "Moons of Peril", "Barbarian Assault/Gambles": "Barbarian Assault",
    "Kalphite Queen": "Kalphite Queen", "Enormous Tentacle": "Kraken",
    "Phosani's Nightmare": "Phosani's Nightmare", "The Nightmare": "The Nightmare",
    "Dossier": "Yama", "Hueycoatl": "The Hueycoatl",
    # GWD bodyguards share the general's room
    "Sergeant Strongstack": "General Graardor", "Sergeant Steelwill": "General Graardor",
    "Sergeant Grimspike": "General Graardor", "Wingman Skree": "Kree'arra",
    "Flight Kilisa": "Kree'arra", "Flockleader Geerin": "Kree'arra",
    "Starlight": "Commander Zilyana", "Growler": "Commander Zilyana",
    "Bree": "Commander Zilyana", "Tstanon Karlak": "K'ril Tsutsaroth",
    "Zakl'n Gritch": "K'ril Tsutsaroth", "Balfrug Kreeyath": "K'ril Tsutsaroth",
}
SOURCE_PREFIX_ALIASES = [("Revenant ", "Revenants")]
# Rewards with no drop/collection-log source data on the wiki (or whose only
# source is a minigame/quest). name -> list of (from, page, rate, kind)
EXTRA_SOURCES = {
    "Fire cape": [("TzHaar Fight Cave", "TzHaar Fight Cave", "Always", "reward")],
    "Infernal cape": [("Inferno", "Inferno", "Always", "reward")],
    "Fighter torso": [("Barbarian Assault", "Barbarian Assault", None, "other")],
    "Fighter hat": [("Barbarian Assault", "Barbarian Assault", None, "other")],
    "Barrows gloves": [("Recipe for Disaster", "Culinaromancer's Chest", None, "other")],
    "Dragon gloves": [("Recipe for Disaster", "Culinaromancer's Chest", None, "other")],
    "Rune gloves": [("Recipe for Disaster", "Culinaromancer's Chest", None, "other")],
    "Adamant gloves": [("Recipe for Disaster", "Culinaromancer's Chest", None, "other")],
    "Mithril gloves": [("Recipe for Disaster", "Culinaromancer's Chest", None, "other")],
    "Dizana's quiver": [("Fortis Colosseum", "Fortis Colosseum", "Always", "reward")],
    "Blessed Dizana's quiver": [("Fortis Colosseum", "Fortis Colosseum", "Always", "reward")],
    "Quiver (Colosseum)": [("Fortis Colosseum", "Fortis Colosseum", "Always", "reward")],
    "Ava's accumulator": [("Animal Magnetism", "Animal Magnetism", None, "other")],
    "Ava's assembler": [("Dragon Slayer II", "Ava's assembler", None, "other")],
    "Ava's attractor": [("Animal Magnetism", "Animal Magnetism", None, "other")],
    "Book of Darkness": [("Horror from the Deep", "Horror from the Deep", None, "other")],
    "Book of Law": [("Horror from the Deep", "Horror from the Deep", None, "other")],
    "Book of War": [("Horror from the Deep", "Horror from the Deep", None, "other")],
    "Book of Balance": [("Horror from the Deep", "Horror from the Deep", None, "other")],
    "Holy book": [("Horror from the Deep", "Horror from the Deep", None, "other")],
    "Unholy book": [("Horror from the Deep", "Horror from the Deep", None, "other")],
    "Mage's book": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Master wand": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Infinity hat": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Infinity top": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Infinity bottoms": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Infinity gloves": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Infinity boots": [("Mage Training Arena", "Mage Training Arena", None, "other")],
    "Helm of Neitiznot": [("The Fremennik Isles", "The Fremennik Isles", None, "other")],
    "Neitiznot shield": [("The Fremennik Isles", "The Fremennik Isles", None, "other")],
    "Salve amulet": [("Haunted Mine", "Haunted Mine", None, "other")],
    "Salve amulet (e)": [("Haunted Mine", "Haunted Mine", None, "other")],
    "Salve amulet(ei)": [("Haunted Mine", "Haunted Mine", None, "other")],
    "Elite void top": [("Pest Control", "Void Knight equipment", None, "other")],
    "Elite void robe": [("Pest Control", "Void Knight equipment", None, "other")],
    "Max cape": [("Mac", "Mac", None, "other")],
    "Mythical cape": [("Dragon Slayer II", "Mythical cape", None, "other")],
    "Cape of Legends": [("Legends' Quest", "Legends' Quest", None, "other")],
    "Proselyte sallet": [("The Slug Menace", "Proselyte armour", None, "other")],
    "Proselyte hauberk": [("The Slug Menace", "Proselyte armour", None, "other")],
    "Proselyte cuisse": [("The Slug Menace", "Proselyte armour", None, "other")],
    "Proselyte tasset": [("The Slug Menace", "Proselyte armour", None, "other")],
    "Initiate sallet": [("Recruitment Drive", "Initiate armour", None, "other")],
    "Initiate hauberk": [("Recruitment Drive", "Initiate armour", None, "other")],
    "Initiate cuisse": [("Recruitment Drive", "Initiate armour", None, "other")],
}
CLOG_KIND = {"drop": "drop", "shop": "other", "manual": "other"}
REWARD_RX = re.compile(r"chest|casket|reward|cache|lockbox|sack|crate|bag\b|box\b|"
                       r"Gambles|impling jar|offering", re.I)
SKIP_SOURCES = {"Rare drop table", "Gem drop table", "Mega-rare drop table"}

# --------------------------------------------------------------------------
# Content access: slayer levels and quests
# --------------------------------------------------------------------------
# Content.name -> infobox_monster page(s) to take the Slayer level from
SLAYER_MONSTERS = {"Grotesque Guardians": ["Dusk", "Dawn"]}
# Content.name -> slayer level, overriding the infobox (None = no requirement)
SLAYER_OVERRIDES = {
    "Amoxliatl": None,   # infobox lists the Lesser Nagua task level; no requirement to fight
    "Wilderness Slayer": None,
}
# Quests strictly needed to access the content (checked against the wiki
# pages, Oct 2026). Content.name -> [quest, ...]
CONTENT_QUESTS = {
    "The Fractured Archive": ["While Guthix Sleeps"],
    "Theatre of Blood": ["Priest in Peril"],
    "Tombs of Amascut": ["Beneath Cursed Sands"],
    "Amoxliatl": ["Children of the Sun", "The Heart of Darkness"],
    "Brutus": ["The Ides of Milk"],
    "Demonic Brutus": ["Desert Treasure II - The Fallen Empire"],
    "Doom of Mokhaiotl": ["Children of the Sun", "The Final Dawn"],
    "Duke Sucellus": ["Desert Treasure II - The Fallen Empire"],
    "The Leviathan": ["Desert Treasure II - The Fallen Empire"],
    "The Whisperer": ["Desert Treasure II - The Fallen Empire"],
    "Vardorvis": ["Desert Treasure II - The Fallen Empire"],
    "Grotesque Guardians": ["Priest in Peril"],
    "Gargoyles": ["Priest in Peril"],
    "Mad Angel": ["Fallen From Grace"],
    "Maggot King": ["The Blood Moon Rises"],
    "Nex": ["Desert Treasure I", "The Frozen Door"],
    "Phantom Muspah": ["Secrets of the North"],
    "The Nightmare": ["Priest in Peril"],
    "Phosani's Nightmare": ["Priest in Peril"],
    "Barrows": ["Priest in Peril"],
    "Shellbane gryphon": ["Troubled Tortugans"],
    "The Hueycoatl": ["Children of the Sun"],
    "Fortis Colosseum": ["Children of the Sun"],
    "Moons of Peril": ["Children of the Sun", "Perilous Moons"],
    "Custodian stalker": ["Children of the Sun", "Shadows of Custodia"],
    "Vorkath": ["Dragon Slayer II"],
    "Adamant dragon": ["Dragon Slayer II"],
    "Rune dragon": ["Dragon Slayer II"],
    "Zulrah": ["Regicide"],
    "Yama": ["A Kingdom Divided"],
    "Xamphur": ["A Kingdom Divided"],
    "Demonic gorilla": ["Monkey Madness II"],
    "Maniacal monkey": ["Monkey Madness II"],
    "Tormented Demon": ["While Guthix Sleeps"],
    "Basilisk Knight": ["The Fremennik Exiles"],
    "Dark beast": ["Mourning's End Part I"],
    "Venator": ["The Blood Moon Rises"],
    "Vyrewatch Sentinel": ["Sins of the Father"],
    "Suqah": ["Lunar Diplomacy"],
}

# --------------------------------------------------------------------------
# Prayers
# --------------------------------------------------------------------------
# name -> (style, unlock sentence or None, unlock item or None, usedAt regex)
PRAYERS = {
    "Protect from Magic": ("all", None, None,
                           r"protect(?:ion)? from magic|\bpray(?:ing)? (?:against )?(?:mage|magic)\b"),
    "Protect from Missiles": ("all", None, None,
                              r"protect(?:ion)? from (?:missiles|ranged?)\b|\bpray(?:ing)? (?:against )?(?:range|ranged|missiles)\b"),
    "Protect from Melee": ("all", None, None,
                           r"protect(?:ion)? from melee|\bpray(?:ing)? (?:against )?melee\b"),
    "Eagle Eye": ("ranged", None, None, r"\beagle eye\b"),
    "Deadeye": ("ranged",
                "Read a Deadeye prayer scroll (untradeable, from Eldric the Ice King at the "
                "Royal Titans); it replaces Eagle Eye.", "Deadeye prayer scroll", r"\bdeadeye\b"),
    "Rigour": ("ranged", "Read a Dexterous prayer scroll (tradeable Chambers of Xeric reward).",
               "Dexterous prayer scroll", r"\brigour\b"),
    "Mystic Might": ("magic", None, None, r"\bmystic might\b"),
    "Mystic Vigour": ("magic",
                      "Read a Mystic vigour prayer scroll (untradeable, from Branda the Fire "
                      "Queen at the Royal Titans); it replaces Mystic Might.",
                      "Mystic vigour prayer scroll", r"\bmystic vigour\b"),
    "Augury": ("magic", "Read an Arcane prayer scroll (tradeable Chambers of Xeric reward).",
               "Arcane prayer scroll", r"\baugury\b"),
    "Incredible Reflexes": ("melee", None, None, r"\bincredible reflexes\b"),
    "Ultimate Strength": ("melee", None, None, r"\bultimate strength\b"),
    "Chivalry": ("melee", "Complete the King's Ransom quest and then the Knight Waves Training "
                 "Ground in Camelot.", None, r"\bchivalry\b"),
    "Piety": ("melee", "Complete the King's Ransom quest and then the Knight Waves Training "
              "Ground in Camelot.", None, r"\bpiety\b"),
    "Zeal": ("melee", "Bring the Horn of Bran (tradeable reward from The Fractured Archive) to "
             "King Arthur in Camelot; it replaces Piety.", "Horn of Bran",
             r"\bzeal\b(?! tokens?)"),
    "Preserve": ("all", "Read a Torn prayer scroll (tradeable Chambers of Xeric reward).",
                 "Torn prayer scroll", r"\[\[(?:file:)?preserve\b|\bpreserve prayer"),
}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
CACHE = os.environ.get("GEAR_CACHE")
_last_wiki = [0.0]


def get(url, params=None, polite=False):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    if CACHE:
        path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf8") as f:
                return json.load(f)
    if polite:  # sequential + ~1s between wiki API calls
        wait = 1.0 - (time.time() - _last_wiki[0])
        if wait > 0:
            time.sleep(wait)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            break
        except Exception as e:  # noqa: BLE001 - retry transient errors
            if attempt == 3:
                raise
            print(f"  retry ({e})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    _last_wiki[0] = time.time()
    if CACHE:
        os.makedirs(CACHE, exist_ok=True)
        with open(path, "w", encoding="utf8") as f:
            json.dump(data, f)
    return data


def wiki(**params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", 2)
    return get(API, params, polite=True)


def bucket(query):
    d = wiki(action="bucket", query=query)
    if "error" in d:
        raise RuntimeError(f"bucket error: {d['error']}")
    return d["bucket"]


def bucket_all(name, fields):
    sel = ",".join(f"'{f}'" for f in fields)
    out, offset = [], 0
    while True:
        chunk = bucket(f"bucket('{name}').select({sel}).limit(5000).offset({offset}).run()")
        out += chunk
        if len(chunk) < 5000:
            return out
        offset += 5000


def chunks(seq, n=50):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def page_categories(titles, cats):
    """title -> set of the given categories it belongs to (after redirects)."""
    out = {}
    for batch in chunks(titles):
        d = wiki(action="query", prop="categories", titles="|".join(batch),
                 clcategories="|".join(cats), cllimit="max", redirects=1)
        q = d.get("query", {})
        fwd = {r["from"]: r["to"] for k in ("normalized", "redirects") for r in q.get(k, [])}
        pages = {p["title"]: {c["title"] for c in p.get("categories", [])}
                 for p in q.get("pages", [])}
        for t in batch:
            u = t
            for _ in range(3):
                u = fwd.get(u, u)
            out[t] = pages.get(u, set())
    return out


def resolve_titles(titles):
    """title -> (canonical title, fragment, exists, is_disambig)."""
    out = {}
    for batch in chunks(sorted(titles)):
        d = wiki(action="query", titles="|".join(batch), redirects=1,
                 prop="pageprops", ppprop="disambiguation")
        q = d.get("query", {})
        norm = {r["from"]: r["to"] for r in q.get("normalized", [])}
        redir = {r["from"]: (r["to"], r.get("tofragment", "")) for r in q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", [])}
        for t in batch:
            n = norm.get(t, t)
            target, frag = redir.get(n, (n, ""))
            p = pages.get(target, {})
            out[t] = (target, frag, not p.get("missing", False) and bool(p),
                      "disambiguation" in p.get("pageprops", {}))
    return out


def page_texts(titles):
    """title -> wikitext of the page (titles must be canonical)."""
    out = {}
    for batch in chunks(titles):
        d = wiki(action="query", prop="revisions", rvprop="content", rvslots="main",
                 titles="|".join(batch))
        for p in d.get("query", {}).get("pages", []):
            revs = p.get("revisions")
            if revs:
                out[p["title"]] = revs[0]["slots"]["main"].get("content", "")
    return out


def category_members(cat):
    out, cont = [], {}
    while True:
        d = wiki(action="query", list="categorymembers", cmtitle=cat, cmlimit=500,
                 cmnamespace=0, **cont)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" not in d:
            return out
        cont = d["continue"]


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def slug(s):
    s = s.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def clean_caption(s):
    if not s:
        return ""
    s = re.sub(r"\[\[File:[^\]]*\]\]", "", s)
    s = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"'\"`UNIQ--.*?QINU`\"'", "", s)
    # table-attribute junk: `style="white-space:nowrap;" |`, `clear:both;`
    s = re.sub(r"^[^|]*=\s*\"[^\"]*\"\s*\|", "", s)
    s = re.sub(r"\b[a-z-]+:\s*[a-z0-9-]+;", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip(" |")


STYLE_WORDS = [
    ("melee", r"\bmelee\b|\bstab\b|\bslash\b|\bcrush\b|dharok|tank\b|hallowfell"),
    ("ranged", r"\branged?\b|\bcrossbow|\bbow\b|bowfa|tbow|chinchompa|atlatl"),
    ("magic", r"\bmagic\b|\bmage\b|barrage|\bburst\b|tumeken"),
]


def style_from_caption(label):
    s = (label or "").lower()
    if re.search(r"hybrid|tribrid", s):
        return "mixed"
    hits = [k for k, rx in STYLE_WORDS if re.search(rx, s)]
    # "Melee Tank" / "Mage tank" -> first explicit style word wins
    explicit = [k for k in ("melee", "ranged", "magic")
                if re.search({"melee": r"\bmelee\b", "ranged": r"\branged?\b",
                              "magic": r"\bmagic\b|\bmage\b"}[k], s)]
    if len(explicit) == 1:
        return explicit[0]
    if len(explicit) > 1:
        return "mixed"
    return hits[0] if len(set(hits)) == 1 else None


RANGED_WEAPONS = {"thrown", "bow", "crossbow", "chinchompas", "gun", "blaster"}
MAGIC_WEAPONS = {"staff", "powered staff", "bladed staff", "powered wand"}


def bonus_style(b):
    """Combat style an item favours according to its infobox bonuses."""
    if not b:
        return None
    cs = (b.get("combat_style") or "").lower()
    if cs in RANGED_WEAPONS:
        return "ranged"
    if cs in MAGIC_WEAPONS:
        return "magic"
    g = lambda k: b.get(k) or 0  # noqa: E731
    melee = max(g("stab_attack_bonus"), g("slash_attack_bonus"),
                g("crush_attack_bonus")) + g("strength_bonus")
    ranged = g("range_attack_bonus") + g("ranged_strength_bonus")
    magic = g("magic_attack_bonus") + 3 * g("magic_damage_bonus")
    best = max(melee, ranged, magic)
    if best <= 0:
        return None
    winners = [k for k, v in (("melee", melee), ("ranged", ranged), ("magic", magic))
               if v == best]
    return winners[0] if len(winners) == 1 else None


# --------------------------------------------------------------------------
# Requirement parsing from the wiki lead section (primary reqs source)
# --------------------------------------------------------------------------
SKILL_ALT = "|".join(s.capitalize() for s in SKILLS) + "|Range"
REQ_PATTERNS = [
    re.compile(r"\{\{SCP\|(" + SKILL_ALT + r")\|(\d+)", re.I),
    re.compile(r"(\d{1,2})\s*(?:in\s+)?\[\[(" + SKILL_ALT + r")(?:\|[^\]]*)?\]\]", re.I),
    re.compile(r"level[- ](\d{1,2})\s*\[\[(" + SKILL_ALT + r")(?:\|[^\]]*)?\]\]", re.I),
    re.compile(r"\[\[(" + SKILL_ALT + r")(?:\|[^\]]*)?\]\]\s*level\s*(?:of\s*)?(?:at least\s*)?(\d{1,2})", re.I),
    re.compile(r"(?<![+\d])(\d{1,2})\s+(" + SKILL_ALT + r")\b"),  # unlinked "85 Magic"
]
# One level shared by several skills: "level 80 in [[Defence]], [[Strength]],
# [[Ranged]], and [[Magic]]" / "level 80 [[Ranged]] and [[Defence]]"
REQ_LIST = re.compile(r"(?<![+\d])(\d{1,2})\s+(?:in\s+)?((?:\[\[[^\]]+\]\]"
                      r"(?:\s*,\s*(?:and\s+)?|\s+and\s+))+\[\[[^\]]+\]\])", re.I)
EQUIP_WORDS = re.compile(r"\b(wield|wear|equip|use)", re.I)


def lead_text(wt):
    wt = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", wt, flags=re.S)
    wt = re.sub(r"\{\{[Ii]nfobox.*?\n\}\}", "", wt, flags=re.S)
    return wt.split("\n==")[0]


def sentences(text):
    return re.split(r"(?<=[.!?])\s+(?=[A-Z'\[])|\n", text)


NEGATED = re.compile(r"\bnot\b|n't\b|\bno longer\b|\bwithout\b|\bno requirements?\b", re.I)


REQ_START = re.compile(r"requir\w*|\bneeds?\b", re.I)
EQUIP_TO = re.compile(r"\bto\s+(?:wield|wear|equip|use)\b|\bin order to (?:wield|wear|equip)", re.I)
EQUIP_BEFORE = re.compile(r"\b(?:wield|wear|equip)\w*\b[^.]*$", re.I)


def req_windows(sent):
    """Sub-strings of a sentence that state equip requirements, e.g. the
    "requires level 70 [[Magic]], 60 [[Strength]] ... to wield" part."""
    for m in REQ_START.finditer(sent):
        before = sent[max(0, m.start() - 40):m.start()]
        rest = sent[m.end():]
        e = EQUIP_TO.search(rest)
        if e and e.start() < 250:
            win = rest[:e.start()]
        elif EQUIP_BEFORE.search(sent[:m.start()]):   # "Equipping X requires ..."
            win = rest
        else:
            continue
        if NEGATED.search(before + m.group(0) + win):
            continue
        yield win


def parse_levels(win):
    reqs = {}
    for rx in REQ_PATTERNS:
        for m in rx.finditer(win):
            a, b = m.groups()
            skill, lvl = (a, b) if not a.isdigit() else (b, a)
            skill = skill.lower()
            skill = "ranged" if skill == "range" else skill
            lvl = int(lvl)
            if 1 < lvl <= 99 and skill in SKILLS:
                reqs[skill] = max(reqs.get(skill, 0), lvl)
    for m in REQ_LIST.finditer(win):
        lvl = int(m.group(1))
        for sk in re.findall(r"\[\[([^|\]]+)", m.group(2)):
            sk = sk.strip().lower()
            sk = "ranged" if sk == "range" else sk
            if sk in SKILLS and 1 < lvl <= 99:
                reqs[sk] = max(reqs.get(sk, 0), lvl)
    return reqs


def reqs_from_wikitext(wt):
    """Equip requirements stated in the lead section; the first sentence that
    states any wins (later sentences tend to talk about other items)."""
    for sent in sentences(lead_text(wt)):
        for win in req_windows(sent):
            reqs = parse_levels(win)
            if reqs:
                return reqs
    return {}


def quests_from_wikitext(wt, quest_names):
    found = []
    for sent in sentences(lead_text(wt)):
        if not re.search(r"\b(wield|wear|equip)", sent, re.I):
            continue
        if not re.search(r"complet|requir|started", sent, re.I) or NEGATED.search(sent):
            continue
        for t in re.findall(r"\[\[([^|\]#]+)", sent):
            t = t.strip().replace("_", " ")
            t = t[0].upper() + t[1:] if t else t
            if t in quest_names and "/" not in t and t not in found:
                found.append(t)
    return found


# --------------------------------------------------------------------------
# Sources (drops, collection log, recipes)
# --------------------------------------------------------------------------
def lua_str(s):
    return json.dumps(s, ensure_ascii=False)


def bucket_where_in(name, fields, key, values, n=50):
    """Rows of `name` whose `key` is any of `values` (bucket.Or, n per request)."""
    sel = ",".join(f"'{f}'" for f in fields)
    out = []
    for batch in chunks(sorted(set(values)), n):
        cond = ",".join("{'%s',%s}" % (key, lua_str(v)) for v in batch)
        offset = 0
        while True:
            chunk = bucket(f"bucket('{name}').select({sel}).where(bucket.Or({cond}))"
                           f".limit(5000).offset({offset}).run()")
            out += chunk
            if len(chunk) < 5000:
                break
            offset += 5000
    return out


FRACTION = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
MULT = re.compile(r"^\s*(\d+)\s*[×x]\s*")


def rate_prob(rate):
    """Approximate chance per kill/opening for sorting; None if not numeric."""
    if not rate:
        return None
    if rate.strip().lower() == "always":
        return 1.0
    s = rate.replace(",", "")
    m = FRACTION.search(s)
    if not m or float(m.group(2)) == 0:
        return None
    p = float(m.group(1)) / float(m.group(2))
    mm = MULT.match(s)
    if mm:
        p = min(1.0, p * int(mm.group(1)))
    return p


def clean_rate(r):
    r = html.unescape(r or "").strip()
    r = re.sub(r"\s*×\s*", " × ", r)
    return r or None


def norm_name(s):
    """lower-case singular form for loose name matching."""
    s = re.sub(r"\s*\(.*?\)\s*", " ", s).strip().lower()
    if s.endswith("ies"):
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith("ss"):
        return s[:-1]
    return s


class ContentMatcher:
    """Maps a monster/chest name to one of our Content ids."""

    def __init__(self, contents, monsters):
        self.by_name = {c["name"].lower(): c["id"] for c in contents.values()}
        self.by_norm = {norm_name(c["name"]): c["id"] for c in contents.values()}
        # monster page -> slayer categories (to map superiors etc. to the task)
        self.cats = defaultdict(set)
        for m in monsters:
            for cat in m.get("slayer_category") or []:
                if cat != "Bosses":
                    self.cats[m["page_name"]].add(cat)

    def __call__(self, name):
        alias = SOURCE_ALIASES.get(name)
        if alias:
            return self.by_name.get(alias.lower())
        for pre, target in SOURCE_PREFIX_ALIASES:
            if name.startswith(pre):
                return self.by_name.get(target.lower())
        hit = self.by_name.get(name.lower()) or self.by_norm.get(norm_name(name))
        if hit:
            return hit
        for cat in sorted(self.cats.get(name, ())):
            hit = self.by_norm.get(norm_name(cat))
            if hit:
                return hit
        return None


def parse_clog_link(s):
    """'[[Ancient chest#Normal Mode|Ancient chest (Normal Mode)]]' -> 'Ancient chest'."""
    m = re.fullmatch(r"\s*\[\[([^|\]#]+)(?:#[^|\]]*)?(?:\|[^\]]*)?\]\]\s*", s or "")
    return m.group(1).strip() if m else None


def build_sources(names, ids_of, matcher):
    """name -> [Source] for every name in `names` (items and unlock scrolls).

    1. Bucket `dropsline` (monster drop tables and reward chests), queried with
       bucket.Or in batches of 50 names.
    2. Bucket `collection_log_source` (whole bucket; matched by item id, then
       by name) for minigame shops and rewards with no drop table.
    3. Items with neither are traced through Bucket `recipe` (up to 3 levels):
       they inherit the sources of their most valuable obtainable component
       (Bandos godsword -> Bandos hilt, Torva platebody -> Torva platebody
       (damaged), Ultor ring -> Ultor icon -> Ultor vestige).
    4. EXTRA_SOURCES fills quest/minigame rewards the wiki has no table for.
    """
    clog = bucket_all("collection_log_source", ["item_id", "item_name", "sources",
                                                "rates", "kinds"])
    clog_by_id = defaultdict(list)
    clog_by_name = defaultdict(list)
    for r in clog:
        clog_by_id[r.get("item_id")].append(r)
        clog_by_name[(r.get("item_name") or "").split("#")[0]].append(r)

    raw = defaultdict(list)       # name -> [(from, page, rate, kind)]
    value = {}                    # name -> alch value of its drop (component choice)

    def fetch_drops(want):
        # charged items drop as "X (uncharged)" (Tumeken's shadow, Eye of Ayak...)
        back = {n: n for n in want}
        for n in want:
            back.setdefault(f"{n} (uncharged)", n)
        for r in bucket_where_in("dropsline", ["page_name", "item_name", "drop_json"],
                                 "item_name", back):
            r["item_name"] = back.get(r["item_name"], r["item_name"])
            try:
                d = json.loads(r["drop_json"])
            except (TypeError, ValueError):
                continue
            page = r["page_name"]
            frm = (d.get("Dropped from") or page).split("#")[0].strip()
            if page in SKIP_SOURCES or frm in SKIP_SOURCES:
                continue
            rate = clean_rate(d.get("Rarity"))
            rolls = d.get("Rolls") or 1
            if rate and isinstance(rolls, int) and rolls > 1 and FRACTION.search(rate):
                rate = f"{rolls} × {rate}"
            dt = (d.get("Drop type") or "").lower()
            kind = {"combat": "drop", "reward": "reward"}.get(dt, "other")
            raw[r["item_name"]].append((frm, page, rate, kind))
            try:
                q = max(1, int(d.get("Quantity Low") or 1))
                value[r["item_name"]] = max(value.get(r["item_name"], 0),
                                            int(d.get("Drop Value") or 0) // q)
            except (TypeError, ValueError):
                pass

    def add_clog(name, ids=()):
        rows = [r for i in ids for r in clog_by_id.get(i, [])] or clog_by_name.get(name, [])
        seen = set()
        for r in rows:
            key = (r.get("item_id"), r.get("item_name"))
            if key in seen:
                continue
            seen.add(key)
            for src, rate, kind in zip(r.get("sources") or [], r.get("rates") or [],
                                       r.get("kinds") or []):
                if kind not in CLOG_KIND:
                    continue          # recipes are handled through Bucket `recipe`
                page = parse_clog_link(src)
                if not page or page in SKIP_SOURCES:
                    continue
                k = CLOG_KIND[kind]
                if k == "drop" and REWARD_RX.search(page):
                    k = "reward"
                raw[name].append((page, page, clean_rate(rate) if k != "other" else None, k))

    names = sorted(set(names))
    fetched = set(names)
    fetch_drops(names)
    for n in names:
        add_clog(n, ids_of(n))

    # recipe fallback: find the item's key component. A component "belongs" to
    # the item when it shares its first word (Ultor ring <- Ultor icon <- Ultor
    # vestige); otherwise any component with only a few sources (a unique, not a
    # rune or bar) will do, the most valuable first.
    def nsrc(m):
        return len({s[0] for s in raw.get(m, [])})

    def related(target, m):
        w = re.findall(r"[a-z']+", target.lower())
        return bool(w) and w[0] not in GENERIC_WORDS and w[0] in re.findall(r"[a-z']+", m.lower())

    resolved = {n: n for n in names if raw.get(n)}
    def key_parts(n):
        k = KEY_COMPONENTS.get(n, [])
        return [k] if isinstance(k, str) else k

    keys = sorted({k for n in names if n not in resolved for k in key_parts(n)})
    fetch_drops([k for k in keys if k not in fetched])
    fetched.update(keys)
    for k in keys:
        add_clog(k)
    for n in names:
        parts = [k for k in key_parts(n) if raw.get(k)]
        if parts and n not in resolved:
            if len(parts) > 1:      # merged pseudo-entry for multi-part items
                raw["\0" + n] = [row for k in parts for row in raw[k]]
                parts = ["\0" + n]
            resolved[n] = parts[0]
    pending = {n: {n} for n in names if n not in resolved and n not in EXTRA_SOURCES}
    visited = defaultdict(set)
    fallback = {}
    for _depth in range(4):
        if not pending:
            break
        recipes = defaultdict(list)
        for r in bucket_where_in("recipe", ["page_name", "uses_material"], "page_name",
                                 {c for fr in pending.values() for c in fr}):
            recipes[r["page_name"]].append(r.get("uses_material") or [])
        mats = {m for ms in recipes.values() for mat in ms for m in mat}
        new_mats = sorted(m for m in mats if m not in raw and m not in fetched)
        fetched.update(new_mats)
        fetch_drops(new_mats)
        for m in new_mats:
            add_clog(m)
        nxt = {}
        for target, frontier in pending.items():
            visited[target] |= frontier
            opts = sorted({m for c in frontier for ms in recipes.get(c, []) for m in ms}
                          - visited[target] - {target})
            uniq = [m for m in opts if 0 < nsrc(m) <= MAX_COMPONENT_SOURCES
                    and not COMMODITY_RX.search(m)]
            rel = [m for m in opts if related(target, m)]
            pick = [m for m in rel if m in uniq] or ([] if rel else uniq)
            best = lambda ms: max(ms, key=lambda m: (value.get(m, 0), -nsrc(m), m))  # noqa: E731
            if pick:
                resolved[target] = best(pick)
            elif rel:
                nxt[target] = set(rel)
                if uniq and target not in fallback:
                    fallback[target] = best(uniq)
            else:
                follow = {m for m in opts if not raw.get(m)}
                if follow:
                    nxt[target] = follow
        pending = nxt
    for target, comp in fallback.items():
        resolved.setdefault(target, comp)

    out = {}
    for n in names:
        rows = list(raw.get(resolved[n], [])) if n in resolved else []
        for frm, page, rate, kind in EXTRA_SOURCES.get(n, []):
            rows.append((frm, page, rate, kind))
        best = {}
        for frm, page, rate, kind in rows:
            p = rate_prob(rate)
            cur = best.get(frm)
            if cur is None or (p or -1) > (cur["_p"] or -1):
                best[frm] = {"from": frm, "page": page, "rate": rate, "kind": kind,
                             "contentId": matcher(frm), "_p": p}
        srcs = sorted(best.values(), key=lambda s: (s["_p"] is None, -(s["_p"] or 0),
                                                     s["contentId"] is None, s["from"]))
        for s in srcs[:MAX_SOURCES]:
            del s["_p"]
        out[n] = srcs[:MAX_SOURCES]
    via = {n: resolved[n].lstrip(chr(0)) or n for n in names if resolved.get(n, n) != n}
    return out, via


# --------------------------------------------------------------------------
# Content access
# --------------------------------------------------------------------------
def slayer_levels(contents, monsters):
    by_page = {}
    by_cat = defaultdict(list)
    for m in monsters:
        lvl = m.get("slayer_level")
        if not lvl or lvl <= 1:
            continue
        by_page.setdefault(norm_name(m["page_name"]), lvl)
        for cat in m.get("slayer_category") or []:
            if cat != "Bosses":
                by_cat[norm_name(cat)].append(lvl)
    out = {}
    for c in contents.values():
        name = c["name"]
        if name in SLAYER_OVERRIDES:
            out[c["id"]] = SLAYER_OVERRIDES[name]
            continue
        lvl = None
        for mon in SLAYER_MONSTERS.get(name, [name]):
            lvl = by_page.get(norm_name(mon))
            if lvl:
                break
        if not lvl and by_cat.get(norm_name(name)):
            lvl = min(by_cat[norm_name(name)])
        out[c["id"]] = lvl
    return out


# --------------------------------------------------------------------------
# Prayers
# --------------------------------------------------------------------------
def infobox_fields(wt, name):
    m = re.search(r"\{\{\s*Infobox " + name + r"(.*?)\n\}\}", wt, re.S | re.I)
    if not m:
        return {}, wt
    fields = {k.strip(): v.strip() for k, v in
              re.findall(r"^\|\s*([\w ]+?)\s*=\s*(.*)$", m.group(1), re.M)}
    return fields, wt[m.end():]


def strip_markup(s):
    s = re.sub(r"\{\{[^{}]*\}\}", "", s or "")
    return clean_caption(s)


def prayer_reqs(level, body):
    """Prayer level from the infobox plus other skills the lead says are needed
    to use it ("requiring 74 Prayer and 70 [[Defence]]")."""
    reqs = {"prayer": int(level)} if str(level).isdigit() else {}
    body = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", body, flags=re.S)
    for para in body.split("\n==")[0].split("\n\n")[:3]:
        for sent in sentences(para):
            # sentences about the *other* prayer it upgrades to/from
            if re.search(r"replaced by|upgraded into|By reading", sent):
                continue
            if not re.search(r"requir|having level|level of", sent, re.I):
                continue
            for sk, lv in parse_levels(sent).items():
                if sk != "prayer":
                    reqs[sk] = max(reqs.get(sk, 0), lv)
    return {k: reqs[k] for k in SKILLS if reqs.get(k)}


def build_prayers(scroll_info, page_text):
    """PRAYERS -> [Prayer]. `scroll_info(name)` -> scroll dict or None;
    `page_text` -> {content id: lowercase wikitext of its strategy pages}."""
    texts = page_texts(list(PRAYERS))
    out = []
    for name, (style, unlock, scroll, rx) in PRAYERS.items():
        wt = texts.get(name, "")
        f, body = infobox_fields(wt, "Prayer")
        img = re.search(r"\[\[File:([^|\]]+)", f.get("image", ""))
        effect = strip_markup(re.sub(r"\s*\(Drain:[^)]*\)", "", f.get("effect", "")))
        pat = re.compile(rx, re.I)
        used = [cid for cid, t in page_text.items() if pat.search(t)]
        out.append({
            "name": name,
            "image": img.group(1).strip() if img else f"{name}.png",
            "reqs": prayer_reqs(f.get("level", ""), body),
            "style": style,
            "effect": effect,
            "unlock": unlock,
            "scroll": scroll_info(scroll) if scroll else None,
            "usedAt": used,
        })
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def classify_pages(rows):
    """page_name -> (content name, category) or None, plus excluded list."""
    base_of = {}
    for r in rows:
        p = r["page_name"]
        base_of[p] = p if p.startswith("Slayer task/") else p.split("/")[0]
    bases = sorted(set(base_of.values()))
    cats = page_categories([b for b in bases if not b.startswith("Slayer task/")
                            and b not in EXCLUDE], WIKI_CATS)
    result, excluded = {}, {}
    for page, base in base_of.items():
        why = None
        if base in EXCLUDE:
            why = EXCLUDE[base]
        elif any(rx.search(base) for rx in EXCLUDE_PATTERNS):
            why = "guide / achievement pattern"
        if why:
            excluded[page] = why
            continue
        if base.startswith("Slayer task/"):
            name, cat = base[len("Slayer task/"):], "slayer"
        else:
            name = base
            c = cats.get(base, set())
            cat = CATEGORY_OVERRIDES.get(base)
            if not cat:
                if "Category:Raids" in c:
                    cat = "raid"
                elif "Category:Bosses" in c and "Category:Wilderness" in c:
                    cat = "wilderness"
                elif "Category:Bosses" in c:
                    cat = "boss"
                elif "Category:Slayer monsters" in c:
                    cat = "slayer"
        if not cat:
            excluded[page] = "not in a combat category"
            continue
        name = ALIASES.get(name, name)
        result[page] = (name, cat)
    return result, excluded


def main(out_path):
    t0 = time.time()
    print("Fetching recommended equipment tables...")
    rows = bucket("bucket('recommended_equipment').select('page_name','json')"
                  ".limit(5000).run()")
    print(f"  {len(rows)} tables")
    page_map, excluded = classify_pages(rows)

    # ---- parse tables -----------------------------------------------------
    raw_setups = []          # (content name, page, label, {slot: [[(target, display, file)]]})
    all_targets = set()
    def main_page_first(r):
        p = r["page_name"]
        is_main = p.startswith("Slayer task/") or (p.count("/") == 1 and p.endswith("/Strategies"))
        return (not is_main, p)

    for r in sorted(rows, key=main_page_first):   # stable: keeps table order
        if r["page_name"] not in page_map:
            continue
        name, _ = page_map[r["page_name"]]
        data = json.loads(r["json"])
        eq = data.get("Recommended Equipment", {})
        slots = {}
        for raw_slot, cells in eq.items():
            slot = "weapon" if raw_slot == "2h" else raw_slot
            if slot not in SLOTS:
                continue
            tiers = slots.setdefault(slot, [])
            for ti, cell in enumerate(cells[:MAX_TIERS]):
                while len(tiers) <= ti:
                    tiers.append([])
                for fname, target in PLINK_RE.findall(cell):
                    target = target.strip().replace("_", " ")
                    # display text of the link that follows the plink image
                    m = re.search(r"link=" + re.escape(target) + r"\]\]</span>\[\[[^|\]]+\|([^\]]+)\]\]",
                                  cell.replace("_", " "))
                    disp = clean_caption(m.group(1)) if m else target
                    tiers[ti].append((target, disp, fname.strip()))
                    all_targets.add(target.split("#")[0])
                    if "#" in target:
                        all_targets.add(disp)
        raw_setups.append((name, r["page_name"], data.get("style"), slots))

    # ---- canonical names ---------------------------------------------------
    print(f"Resolving {len(all_targets)} item titles...")
    resolved = resolve_titles(all_targets)

    print("Fetching item infoboxes...")
    ii_rows = bucket_all("infobox_item", ["page_name", "page_name_sub", "item_name",
                                          "item_id", "image", "is_members_only",
                                          "tradeable", "version_anchor", "default_version"])
    ib_rows = bucket_all("infobox_bonuses", [
        "page_name", "page_name_sub", "equipment_slot", "weapon_attack_speed",
        "combat_style", "stab_attack_bonus", "slash_attack_bonus", "crush_attack_bonus",
        "range_attack_bonus", "magic_attack_bonus", "strength_bonus",
        "ranged_strength_bonus", "magic_damage_bonus"])
    infobox = defaultdict(list)
    for r in ii_rows:
        infobox[r["page_name"]].append(r)
    bonuses = defaultdict(list)
    for r in ib_rows:
        bonuses[r["page_name"]].append(r)
    print(f"  {len(ii_rows)} item versions, {len(ib_rows)} bonus versions")

    def canon(target, disp):
        """plink target -> (canonical item name, version fragment)."""
        page, _, frag = target.partition("#")
        title, rfrag, exists, disamb = resolved.get(page, (page, "", False, False))
        frag = frag or rfrag
        if frag and title not in infobox:
            # section link into a group page (e.g. God capes#Imbuing): use the
            # display text if it names a real page, else keep the link text
            t2, f2, ex2, _ = resolved.get(disp, (disp, "", False, False))
            if ex2 and t2 in infobox:
                return t2, f2
            return disp, ""
        if not exists:
            return page, frag
        return title, frag

    # ---- build content ------------------------------------------------------
    contents = {}
    item_seen = {}            # name -> {"files": Counter, "frag": first fragment}
    for name, page, caption, slots in raw_setups:
        cat = page_map[page][1]
        c = contents.setdefault(name, {"id": slug(name), "name": name, "category": cat,
                                       "pages": [], "setups": []})
        if page not in c["pages"]:
            c["pages"].append(page)
        out_slots = {}
        for slot in SLOTS:
            if slot not in slots:
                continue
            used, tiers = set(), []
            for tier in slots[slot]:
                names = []
                for target, disp, fname in tier:
                    n, frag = canon(target, disp)
                    rec = item_seen.setdefault(n, {"files": Counter(), "frag": frag})
                    rec["files"][fname] += 1
                    if n in used:
                        continue
                    used.add(n)
                    names.append(n)
                tiers.append(names)
            while tiers and not tiers[-1]:
                tiers.pop()
            if any(tiers):
                out_slots[slot] = tiers
        if not out_slots:
            continue
        # label
        label = clean_caption(caption)
        label = label[:1].upper() + label[1:]
        sub = page.split("/")[1:] if not page.startswith("Slayer task/") else []
        mode = next((s for s in sub if s not in ("Strategies", "Strategy")), None)
        if mode and mode.lower() not in label.lower():
            label = f"{mode}: {label}" if label else mode
        c["setups"].append({"label": label, "_caption": caption or "", "slots": out_slots})

    # setup styles
    def item_bonus(n):
        bs = bonuses.get(n)
        return bs[0] if bs else None

    for c in contents.values():
        # drop exact duplicate tables
        seen, uniq = set(), []
        for s in c["setups"]:
            key = json.dumps([s["label"], s["slots"]], sort_keys=True)
            if key not in seen:
                seen.add(key)
                uniq.append(s)
        c["setups"] = uniq
        for i, s in enumerate(c["setups"], 1):
            st = style_from_caption(s["label"])
            if st is None:
                weap = (s["slots"].get("weapon") or [[]])[0]
                votes = Counter(filter(None, (bonus_style(item_bonus(n)) for n in weap)))
                if not votes:
                    firsts = [t[0] for sl, t in s["slots"].items()
                              if sl not in ("special", "weapon") and t]
                    votes = Counter(filter(None, (bonus_style(item_bonus(n))
                                                  for f in firsts for n in f)))
                if votes:
                    top, cnt = votes.most_common(1)[0]
                    st = top if cnt / sum(votes.values()) > 0.5 else "mixed"
                else:
                    st = "mixed"
            s["style"] = st
            if not s["label"]:
                s["label"] = {"melee": "Melee", "ranged": "Ranged", "magic": "Magic"}.get(
                    st, f"Setup {i}")
            del s["_caption"]
        # make duplicate labels unique
        cnt = Counter(s["label"] for s in c["setups"])
        idx = Counter()
        for s in c["setups"]:
            if cnt[s["label"]] > 1:
                idx[s["label"]] += 1
                s["label"] = f"{s['label']} ({idx[s['label']]})"
        # best page
        pages = c["pages"]
        pick = next((p for p in pages if p.startswith("Slayer task/")), None) \
            or next((p for p in pages if p.count("/") == 1 and p.endswith("/Strategies")), None) \
            or min(pages, key=len)
        c["page"] = pick

    contents = {k: v for k, v in contents.items() if v["setups"]}

    # ---- item stats from appearances -----------------------------------------
    appear_slot = defaultdict(Counter)
    appear_style = defaultdict(Counter)
    # best tier per (item, slot, content): an item is only scored in its primary
    # slot, so spec weapons (Dragon claws...) don't inflate the main-weapon ranking.
    best_by_slot = defaultdict(lambda: defaultdict(dict))
    for c in contents.values():
        for s in c["setups"]:
            for slot, tiers in s["slots"].items():
                for ti, names in enumerate(tiers, 1):
                    for n in names:
                        appear_slot[n][slot] += 1
                        appear_style[n][s["style"]] += 1
                        b = best_by_slot[n][slot]
                        if ti < b.get(c["id"], 99):
                            b[c["id"]] = ti

    # ---- external data ------------------------------------------------------
    print("Fetching price mapping...")
    mapping = get(PRICES)
    price_ids = {m["id"] for m in mapping}
    price_by_name = {m["name"].lower(): m for m in mapping}

    print("Fetching osrsreboxed equipment requirements...")
    reboxed_by_id, reboxed_by_name = {}, {}
    for s in REBOXED_SLOTS:
        try:
            d = get(REBOXED % s)
        except Exception as e:  # noqa: BLE001
            print(f"  warning: reboxed {s}: {e}", file=sys.stderr)
            continue
        for v in d.values():
            req = ((v.get("equipment") or {}).get("requirements")) or {}
            entry = {k: int(x) for k, x in req.items() if k in SKILLS and x and int(x) > 1}
            reboxed_by_id[int(v["id"])] = entry
            for nm in (v.get("wiki_name"), v.get("name")):
                if nm:
                    reboxed_by_name.setdefault(nm, entry)
    print(f"  {len(reboxed_by_id)} reboxed equipment entries")

    names = sorted(appear_slot)
    print(f"Fetching wikitext for {len(names)} item pages...")
    texts = page_texts([n for n in names if n in infobox])
    quest_names = set(category_members("Category:Quests")) | \
        set(category_members("Category:Miniquests"))

    # ---- assemble items --------------------------------------------------------
    items = {}
    stats = Counter()
    req_src = Counter()
    missing_reqs, missing_geid = [], []
    for n in names:
        vers = infobox.get(n, [])
        frag = item_seen[n]["frag"]
        anchor = next((v for v in vers if frag and
                       (v.get("version_anchor") or "").lower() == frag.lower()), None)
        default = next((v for v in vers if v.get("default_version")), vers[0] if vers else None)
        primary = anchor or default

        def ids(v):
            return [int(x) for x in (v.get("item_id") or []) if str(x).isdigit()]

        # geId: prefer a version with a GE price (anchor, then default, then any)
        geid = None
        ordered = [v for v in (anchor, default) if v] + vers
        for v in ordered:
            for i in ids(v):
                if i in price_ids:
                    geid = i
                    break
            if geid:
                break
        tradeable = any(v.get("tradeable") for v in vers) if vers else False
        if geid is None and (tradeable or not vers):
            m = price_by_name.get(n.lower())
            if m:
                geid = m["id"]
        if geid is not None:
            tradeable = True
        stats["tradeable"] += tradeable
        stats["geid"] += tradeable and geid is not None
        if tradeable and geid is None:
            missing_geid.append(n)

        # image
        # The plink file is what the strategy table shows; keep it when it is a
        # real image of this item. Otherwise use the infobox image (fixes ammo,
        # whose plink "X.png" doesn't exist: the infobox has "X 1..5.png").
        img = None
        plink_file = item_seen[n]["files"].most_common(1)[0][0]
        all_imgs = {re.sub(r"^File:", "", f) for v in vers for f in (v.get("image") or [])}
        if plink_file in all_imgs:
            img = plink_file
        elif primary and primary.get("image"):
            imgs = primary["image"]
            img = imgs[-1] if len(imgs) > 1 and re.search(r" \d+\.png$", imgs[-1]) else imgs[0]
        img = re.sub(r"^File:", "", img or plink_file)

        members = any(v.get("is_members_only") for v in vers) if vers else \
            bool(price_by_name.get(n.lower(), {}).get("members", True))

        # speed
        bs = bonuses.get(n, [])
        bsel = next((b for b in bs if primary and b.get("page_name_sub") == primary.get("page_name_sub")),
                    bs[0] if bs else None)
        speed = bsel.get("weapon_attack_speed") if bsel else None

        # requirements: reboxed by id -> reboxed by name -> wikitext -> overrides
        # requirements: the wiki lead ("requires 75 Ranged to wield") is
        # current (the 2025 requirement rebalance raised many, e.g. Twisted bow
        # 75 -> 85) so it wins; osrsreboxed (by item id, all versions merged)
        # fills items whose prose states nothing parseable.
        wiki_reqs = reqs_from_wikitext(texts[n]) if n in texts else {}
        rb = None
        for v in vers:
            for i in ids(v):
                if i in reboxed_by_id:
                    rb = rb or {}
                    for k, x in reboxed_by_id[i].items():
                        rb[k] = max(rb.get(k, 0), x)
        if rb is None and n in reboxed_by_name:
            rb = dict(reboxed_by_name[n])
        if wiki_reqs:
            reqs, src = wiki_reqs, "wiki"
        elif rb:
            reqs, src = rb, "reboxed"
        elif rb is not None:
            reqs, src = {}, "none-stated"     # reboxed knows the item: no reqs
        else:
            reqs, src = None, "none"
        if os.environ.get("GEAR_DEBUG") and wiki_reqs and rb and wiki_reqs != rb:
            print(f"  DIFF {n}: reboxed={rb} wiki={wiki_reqs}")
        quests = quests_from_wikitext(texts[n], quest_names) if n in texts else []
        ov = OVERRIDES.get(n, {})
        if "reqs" in ov:
            reqs, src = dict(ov["reqs"]), "override"
        if "quests" in ov:
            quests = list(ov["quests"])
        if src == "none" and bs:
            missing_reqs.append(n)   # equipment where no source gave a req
        req_src[src] += 1
        reqs = {k: reqs[k] for k in SKILLS if reqs and reqs.get(k)}

        # slot & style
        sc = appear_slot[n]
        slot = max(sc, key=lambda k: (sc[k], -SLOTS.index(k)))
        st = {k: v for k, v in appear_style[n].items() if k != "mixed"}
        if st:
            top = max(st, key=st.get)
            style = top if st[top] / sum(st.values()) >= 0.6 else "all"
        else:
            style = "mixed"

        items[n] = {
            "name": n, "image": img, "slot": slot, "style": style, "geId": geid,
            "members": bool(members), "tradeable": bool(tradeable),
            "speed": int(speed) if speed else None, "reqs": reqs, "quests": quests,
            "best": dict(sorted(best_by_slot[n][slot].items())),
        }

    order = ["raid", "boss", "wilderness", "slayer", "minigame"]
    ordered = sorted(contents.values(), key=lambda c: (order.index(c["category"]), c["name"].lower()))

    # ---- sources, slayer levels, quests ----------------------------------------
    print("Fetching monster slayer data...")
    monsters = bucket("bucket('infobox_monster').select('page_name','slayer_level',"
                      "'slayer_category').where('slayer_level','>',1).limit(5000).run()")
    matcher = ContentMatcher(contents, monsters)
    slayer = slayer_levels(contents, monsters)

    def ids_of(n):
        return [int(x) for v in infobox.get(n, []) for x in (v.get("item_id") or [])
                if str(x).isdigit()]

    scrolls = [s for _, _, s, _ in PRAYERS.values() if s]
    print(f"Fetching drop sources for {len(items) + len(scrolls)} items...")
    sources, via = build_sources(list(items) + scrolls, ids_of, matcher)
    # Crafted items carry their key component's drops; record which component that is.
    # Raid chest rates on the wiki are the item's share of unique ("purple") loot, not a per-raid chance.
    raid_chests = {"Ancient chest", "Monumental chest", "Chest (Tombs of Amascut)"}
    sources = {n: [{**s, "via": via.get(n),
                    "rate": f"{s['rate']} of uniques" if s["from"] in raid_chests and s["rate"] else s["rate"]}
                   for s in lst] for n, lst in sources.items()}
    for n, it in items.items():
        it["sources"] = sources.get(n, [])

    # ---- prayers ---------------------------------------------------------------
    print("Fetching strategy pages and prayers...")
    all_pages = sorted({p for c in ordered for p in c["pages"]})
    strat = page_texts(all_pages)
    page_text = {c["id"]: "\n".join(strat.get(p, "") for p in c["pages"]) for c in ordered}

    def scroll_info(name):
        vers = infobox.get(name, [])
        primary = next((v for v in vers if v.get("default_version")), vers[0] if vers else {})
        imgs = primary.get("image") or [f"File:{name}.png"]
        geid = next((i for i in ids_of(name) if i in price_ids), None)
        return {"name": name, "image": re.sub(r"^File:", "", imgs[0]), "geId": geid,
                "sources": sources.get(name, [])}

    prayers = build_prayers(scroll_info, page_text)

    # ---- output -----------------------------------------------------------------
    content_out = [{"id": c["id"], "name": c["name"], "category": c["category"],
                    "page": c["page"], "setups": c["setups"],
                    "slayerLevel": slayer.get(c["id"]),
                    "quests": list(CONTENT_QUESTS.get(c["name"], []))} for c in ordered]
    unknown_quests = [k for k in CONTENT_QUESTS if k not in contents]
    if unknown_quests:
        print(f"  warning: CONTENT_QUESTS for unknown content: {unknown_quests}", file=sys.stderr)
    # sanity: every referenced name exists
    for c in content_out:
        for s in c["setups"]:
            for tiers in s["slots"].values():
                for names_ in tiers:
                    for n in names_:
                        assert n in items, n
    ids_ = [c["id"] for c in content_out]
    assert len(ids_) == len(set(ids_)), "duplicate content ids"

    out = {"generated": date.today().isoformat(), "content": content_out, "items": items,
           "prayers": prayers}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    # ---- audit report -------------------------------------------------------------
    print("\n=== Included content ===")
    for cat in order:
        cs = [c for c in content_out if c["category"] == cat]
        print(f"[{cat}] ({len(cs)}): " + ", ".join(
            f"{c['name']} ({len(c['setups'])})" for c in cs))
    print(f"\n=== Excluded pages ({len(excluded)}) ===")
    for p in sorted(excluded):
        print(f"  {p}  -- {excluded[p]}")
    n_items = len(items)
    with_reqs = sum(1 for i in items.values() if i["reqs"])
    print(f"\n{len(content_out)} content, "
          f"{sum(len(c['setups']) for c in content_out)} setups, {n_items} items")
    print(f"geId coverage (tradeable items): {stats['geid']}/{stats['tradeable']} "
          f"({100 * stats['geid'] / max(1, stats['tradeable']):.1f}%)")
    if missing_geid:
        print("  tradeable without geId: " + ", ".join(missing_geid))
    print(f"Requirement sources: {dict(req_src)}; items with >=1 skill req: "
          f"{with_reqs}/{n_items} ({100 * with_reqs / n_items:.1f}%)")
    print(f"Items with quest reqs: {sum(1 for i in items.values() if i['quests'])}")
    if missing_reqs:
        print(f"  equipment with unknown reqs ({len(missing_reqs)}): " + ", ".join(missing_reqs))

    with_src = [i for i in items.values() if i["sources"]]
    with_cid = [i for i in with_src if any(s["contentId"] for s in i["sources"])]
    print(f"\nItems with >=1 source: {len(with_src)}/{n_items} "
          f"({100 * len(with_src) / n_items:.1f}%), via a recipe component: {len(via)}; "
          f"with a source mapped to content: {len(with_cid)}/{len(with_src)} "
          f"({100 * len(with_cid) / max(1, len(with_src)):.1f}%)")
    unmapped = Counter(s["from"] for i in items.values() for s in i["sources"]
                       if not s["contentId"] and s["kind"] != "other")
    print("  most common unmapped sources: " + ", ".join(
        f"{k} ({v})" for k, v in unmapped.most_common(25)))
    if os.environ.get("GEAR_DEBUG"):
        print("  no source: " + ", ".join(n for n, i in items.items() if not i["sources"]))
        print("  via component: " + ", ".join(f"{k} <- {v}" for k, v in sorted(via.items())))
    sl = [c for c in content_out if c["slayerLevel"]]
    print(f"Content with a Slayer level: {len(sl)}: " + ", ".join(
        f"{c['name']} {c['slayerLevel']}" for c in sl))
    print(f"Content with quest requirements: {sum(1 for c in content_out if c['quests'])}")
    print("Prayers:")
    for p in prayers:
        sc = p["scroll"]
        print(f"  {p['name']}: reqs={p['reqs']} style={p['style']} usedAt={len(p['usedAt'])}"
              + (f" scroll={sc['name']} geId={sc['geId']} sources={len(sc['sources'])}" if sc else ""))
    print(f"\nWrote {out_path} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join("public", "data", "gear.json"))
