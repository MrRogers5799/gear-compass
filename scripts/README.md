# Data pipeline

`build_data.py` builds `public/data/gear.json` (the `GearData` shape in
`src/types.ts`) from the OSRS Wiki's boss and slayer strategy
"Recommended equipment" tables. It uses only the Python standard library.

```
python -I scripts/build_data.py [out_path]     # default public/data/gear.json
```

A full run takes about 1 minute (about 40 sequential wiki requests, roughly 1s
apart). Two environment variables help during development:
`GEAR_CACHE=<dir>` caches HTTP responses, and `GEAR_DEBUG=1` prints the items
where the two requirement sources disagree.

## Sources

| Data | Source |
|---|---|
| Strategy tables | Wiki Bucket `recommended_equipment` (page_name, json); the first 5 tiers of each slot. `2h` is treated as `weapon` |
| Content categories | Wiki categories (Raids, Bosses, Slayer monsters, Wilderness), plus explicit lists in the script |
| Canonical item names | MediaWiki `action=query&redirects` (in batches of 50) |
| GE id, image, members, tradeable | Bucket `infobox_item` (all versions), plus the price API `mapping` |
| Attack speed, item style | Bucket `infobox_bonuses` |
| Skill requirements | Wiki item-page lead prose (primary), then [osrsreboxed-db](https://github.com/0xNeffarion/osrsreboxed-db) `items-json-slot` (matched by item id), then the `OVERRIDES` dict |
| Quest requirements | Lead sentences about wielding or wearing that link a page in Category:Quests or Category:Miniquests, plus `OVERRIDES` |

No Bucket stores equip requirements (`infobox_item.quest` only marks quest
items). osrsreboxed has been stale since January 2025 and misses the 2025
requirement changes (for example, Twisted bow went from 75 to 85 Ranged, and
Scythe went to 80 Attack / 90 Strength). The wiki prose is current, so the
script uses it first. It only parses the clause between "requires" and
"to wield/wear/equip", and the first sentence that states requirements wins.

## How content is categorised

1. Base page = the text before the first `/`. `Slayer task/X` pages become slayer content named X.
2. Pages listed in `EXCLUDE_GROUPS` or matching `EXCLUDE_PATTERNS` are dropped: skilling activities, training and account guides, combat-achievement and speed-trial pages.
3. `CATEGORY_OVERRIDES` sets the category directly (wilderness bosses, minigames such as the Inferno, Colosseum, Barrows, NMZ and BA). Otherwise the wiki categories decide: Raids → raid, Bosses + Wilderness → wilderness, Bosses → boss, Slayer monsters → slayer. Pages that match none of these are excluded.
4. `ALIASES` merges pages that are the same content (for example `Aquanite/Strategies` and `Slayer task/Aquanites`). Raid sub-pages (CoX Challenge Mode, ToB Hard and Entry Mode) merge into their raid. The setup label gets the mode as a prefix, for example "Hard Mode: Melee".

At the end of each run the script prints the included content by category,
every excluded page with its reason, and coverage stats. Check this output
after the wiki changes.

## Known limitations

- Item names are wiki page names after redirects. Group pages (e.g. "God blessing", "Godsword", "Barrows equipment") stay as single pseudo-items with no GE id or requirements. A section link like `God capes#Imbuing` uses its link text ("Imbued god cape").
- Requirements from the wiki prose are heuristic. Unusual wording can miss a skill or pick one up from a nearby clause. `OVERRIDES` fixes the cases found so far (for example, RFD gloves, where the lead mentions the Defence needed to unlock them).
- Quests are informational. They include quests needed to obtain an item (for example, the Salve amulet's quest), not only hard equip locks. Quests only stated outside the lead are missed.
- Setup style comes from caption keywords, then from the tier-1 weapons' bonuses. Captions like "Tribrid" and "Hybrid" give `mixed`.
- An empty inner tier array means that tier's cell had no item links (notes only). This keeps tier numbers aligned.
- New wiki pages fall back to wiki categories. Check the excluded list for new combat content that needs an override.
