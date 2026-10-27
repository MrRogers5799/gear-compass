# Data pipeline

`build_data.py` builds `public/data/gear.json` (the `GearData` shape in
`src/types.ts`) from the OSRS Wiki's boss and slayer strategy
"Recommended equipment" tables. It uses only the Python standard library.

```
python -I scripts/build_data.py [out_path]     # default public/data/gear.json
```

A full run takes about 2–3 minutes (about 90 sequential wiki requests, roughly
1s apart). Two environment variables help during development:
`GEAR_CACHE=<dir>` caches HTTP responses, and `GEAR_DEBUG=1` prints the items
where the two requirement sources disagree.

## Safety checks (for the unattended weekly run)

- Wiki API errors, which come back as HTTP 200 with an `error` object (ratelimited, `maxlag=5`, readonly...), are retried with backoff. If they persist the run fails, so it never continues with a silently empty result. HTTP and network errors are retried too.
- Bucket queries are paged at the server's 5,000-row cap, which clamps larger limits without an error.
- If any osrsreboxed slot file fails to load, the run fails.
- Before writing, `validate()` checks:
  - minimum content and item counts, and at least 90% of the previous `gear.json`;
  - every prayer has a Prayer level and an effect;
  - requirement coverage of at least 60% and source coverage of at least 75%.
- If a check fails, the script prints the reasons and exits 1, leaving the old file alone. Otherwise the file is replaced atomically.
- If nothing but `generated` would change, the existing file is left untouched, so the workflow makes no commit.

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
| Item sources (`Item.sources`) | Bucket `dropsline` (queried with `bucket.Or` for 50 item names per request, plus each name + " (uncharged)"), Bucket `collection_log_source` (whole bucket, about 1,700 rows, matched by item id), Bucket `recipe` for crafted items, and `EXTRA_SOURCES` |
| Content Slayer level | Bucket `infobox_monster.slayer_level` (rows with a level above 1), plus `SLAYER_MONSTERS` / `SLAYER_OVERRIDES` |
| Content quests | The curated `CONTENT_QUESTS` dict (checked against the wiki pages) |
| Prayers | `{{Infobox Prayer}}` on each prayer page in `PRAYERS` (level, image, effect), with other skill requirements from the lead. Style, unlock sentence and unlock item are curated in `PRAYERS`. The scroll's image and GE id come from `infobox_item` and the price mapping. Its sources work like item sources |
| Prayer `usedAt` | A case-insensitive regex per prayer (in `PRAYERS`), searched in the wikitext of every strategy page merged into each content |

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

## How item sources are built

1. Drop rows: `from` is the "Dropped from" value without its `#variant` (for example "Abyssal demon#Wilderness Slayer Cave" becomes "Abyssal demon"), and `page` is the drop page. The kind is `drop` for drop type `combat`, `reward` for `reward` (chests, raids, Barrows, caskets), and `other` for anything else (thieving, hunter...). When `Rolls` is above 1, the rate is shown as "7 × 1/2,448". Rows from the rare and gem drop tables are skipped.
2. Collection-log rows add sources the drop tables miss. Shops and point stores become `other` with a `null` rate. Collection-log recipe rows are ignored.
3. Items with neither are traced through Bucket `recipe` (up to 4 levels deep), and take the sources of one key component. The script prefers a component that shares the item's first word (Ultor ring → Ultor icon → Ultor vestige), then any component with at most 10 sources that isn't a commodity (`COMMODITY_RX`: runes, bars, wool...), most valuable first. `KEY_COMPONENTS` fixes chains that are too deep or ambiguous (zenyte jewellery → Zenyte shard, Abyssal tentacle → Kraken tentacle, Soulreaper axe → the four DT2 parts). Each source's `via` names the component that row came from.
4. `EXTRA_SOURCES` adds quest and minigame rewards that the wiki has no table for (Fire cape, Infernal cape, Fighter torso, RFD gloves, Mage Training Arena...).
5. Sources with the same `from` are merged, keeping the best rate. They are sorted by approximate chance ("Always" first, non-numeric rates last), and at most 8 are kept.
6. `contentId` is matched in this order: `SOURCE_ALIASES` (Unsired → Abyssal Sire, Dagannoth Rex → Dagannoth Kings, Ancient chest → CoX, Monumental chest → ToB, Dusk → Grotesque Guardians, Eldric/Branda → Royal Titans, GWD bodyguards...), then `SOURCE_PREFIX_ALIASES` ("Revenant …"), then the exact content name, then the singular/plural form ("Abyssal demon" → "Abyssal demons"), then the monster's `infobox_monster.slayer_category` (superiors such as "Greater abyssal demon" or "Nuclear smoke devil" map to their task).

The audit output lists coverage and the most common unmapped sources. With
`GEAR_DEBUG=1` it also lists the items with no source and the item → component
choices.

## Known limitations

- Item names are wiki page names after redirects. Group pages (e.g. "God blessing", "Godsword", "Barrows equipment") stay as single pseudo-items with no GE id or requirements. A section link like `God capes#Imbuing` uses its link text ("Imbued god cape").
- Requirements from the wiki prose are heuristic. Unusual wording can miss a skill or pick one up from a nearby clause. `OVERRIDES` fixes the cases found so far (for example, RFD gloves, where the lead mentions the Defence needed to unlock them).
- Quests are informational. They include quests needed to obtain an item (for example, the Salve amulet's quest), not only hard equip locks. Quests only stated outside the lead are missed.
- Setup style comes from caption keywords, then from the tier-1 weapons' bonuses. Captions like "Tribrid" and "Hybrid" give `mixed`.
- An empty inner tier array means that tier's cell had no item links (notes only). This keeps tier numbers aligned.
- New wiki pages fall back to wiki categories. Check the excluded list for new combat content that needs an override.
- About 15% of items have no source. Most are pseudo-items (Godsword, Arrows, Barrows equipment), skillcapes, achievement-diary rewards and quest rewards that aren't in `EXTRA_SOURCES`. A crafted item's rate is its component's rate.
- The Slayer level is the level on the matching monster's infobox. A task matched by slayer category takes the lowest level in that category (for example, Custodian stalker 54, the juvenile).
- `usedAt` is a text match, so it counts mentions, not recommendations. "Protection prayers" alone doesn't count for any protect prayer.
- "Rite of vile transference" is not a prayer. It's a Yama drop that upgrades the Death Charge spell, so it isn't in `prayers`.
