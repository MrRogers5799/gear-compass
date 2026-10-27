// Shape of public/data/gear.json, produced by scripts/build_data.py.
// Keep the two in sync.

export type Slot =
  | 'head' | 'cape' | 'neck' | 'ammo' | 'weapon' | 'body'
  | 'shield' | 'legs' | 'hands' | 'feet' | 'ring' | 'special';

export type Style = 'melee' | 'ranged' | 'magic' | 'mixed';

export type Category = 'boss' | 'raid' | 'slayer' | 'wilderness' | 'minigame';

export type Skill =
  | 'attack' | 'strength' | 'defence' | 'ranged'
  | 'magic' | 'prayer' | 'hitpoints' | 'slayer';

export interface Setup {
  /** Table caption from the wiki, cleaned of markup, e.g. "Ranged (crossbow)". */
  label: string;
  style: Style;
  /** slot -> tiers (index 0 = tier 1 = best) -> canonical item names sharing that tier */
  slots: Partial<Record<Slot, string[][]>>;
}

export interface Content {
  /** URL-safe slug, e.g. "chambers-of-xeric" */
  id: string;
  /** Display name, e.g. "Chambers of Xeric" or "Gargoyles" */
  name: string;
  category: Category;
  /** Main wiki page to link to, e.g. "Chambers of Xeric/Strategies" */
  page: string;
  /** All recommended-equipment tables for this content (raid rooms, CM, styles...) */
  setups: Setup[];
  /** Slayer level needed to fight it (slayer monsters and slayer bosses), if any */
  slayerLevel: number | null;
  /** Quests needed to access it (curated for the main bosses), empty if none/unknown */
  quests: string[];
}

/** Where an item (or prayer scroll) comes from. */
export interface Source {
  /** Monster/boss/activity name as the wiki writes it, e.g. "Abyssal demon", "Unsired", "Barbarian Assault" */
  from: string;
  /** Wiki page to link to for `from` */
  page: string;
  /** Drop rate as the wiki writes it, e.g. "1/512"; null if not a random drop (shop, minigame points...) */
  rate: string | null;
  /** 'drop' = monster drop table, 'reward' = chest/reward table (raids, Barrows...), 'other' = shop/points/quest */
  kind: 'drop' | 'reward' | 'other';
  /** Matching Content.id when the source is one of our included bosses/raids/slayer tasks */
  contentId: string | null;
  /** For crafted items: the component that actually drops (e.g. "Ultor vestige" for Ultor ring) */
  via: string | null;
}

export interface Prayer {
  name: string;
  /** Wiki file name of the prayer icon, e.g. "Rigour.png" */
  image: string;
  /** All skill levels required, e.g. { prayer: 74, defence: 70 } */
  reqs: Partial<Record<Skill, number>>;
  /** Combat style it boosts ('all' for protection prayers etc.) */
  style: Style | 'all';
  /** Short effect text from the wiki infobox */
  effect: string;
  /** How it's unlocked, one sentence, e.g. "Read a Dexterous prayer scroll (Chambers of Xeric reward)." ; null if available by level alone */
  unlock: string | null;
  /** The tradeable/droppable item that unlocks it, if any */
  scroll: { name: string; image: string; geId: number | null; sources: Source[] } | null;
  /** Content ids whose strategy pages recommend/mention this prayer */
  usedAt: string[];
}

export interface Item {
  /** Canonical wiki page name; also the key in GearData.items */
  name: string;
  /** Wiki file name, e.g. "Abyssal whip.png" -> https://oldschool.runescape.wiki/images/Abyssal_whip.png */
  image: string;
  /** Primary equipment slot ('weapon' covers 2h) */
  slot: Slot;
  /** Dominant combat style across its appearances; 'all' if used by several styles */
  style: Style | 'all';
  /** Item id to look up GE prices with (prices.runescape.wiki), null if untradeable/unknown */
  geId: number | null;
  members: boolean;
  tradeable: boolean;
  /** Attack speed in ticks for weapons */
  speed: number | null;
  /** Skill levels required to equip */
  reqs: Partial<Record<Skill, number>>;
  /** Quests required to equip (informational) */
  quests: string[];
  /** Content id -> best tier the item reaches there (1 = best-in-slot ... 5) */
  best: Record<string, number>;
  /** Where to get it, most likely source first; empty if unknown */
  sources: Source[];
}

export interface GearData {
  /** ISO date of the snapshot */
  generated: string;
  content: Content[];
  items: Record<string, Item>;
  prayers: Prayer[];
}
