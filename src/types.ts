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
}

export interface GearData {
  /** ISO date of the snapshot */
  generated: string;
  content: Content[];
  items: Record<string, Item>;
}
