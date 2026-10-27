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

    # ---- output -----------------------------------------------------------------
    order = ["raid", "boss", "wilderness", "slayer", "minigame"]
    content_out = sorted(contents.values(), key=lambda c: (order.index(c["category"]), c["name"].lower()))
    content_out = [{"id": c["id"], "name": c["name"], "category": c["category"],
                    "page": c["page"], "setups": c["setups"]} for c in content_out]
    # sanity: every referenced name exists
    for c in content_out:
        for s in c["setups"]:
            for tiers in s["slots"].values():
                for names_ in tiers:
                    for n in names_:
                        assert n in items, n
    ids_ = [c["id"] for c in content_out]
    assert len(ids_) == len(set(ids_)), "duplicate content ids"

    out = {"generated": date.today().isoformat(), "content": content_out, "items": items}
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
    print(f"\nWrote {out_path} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join("public", "data", "gear.json"))
