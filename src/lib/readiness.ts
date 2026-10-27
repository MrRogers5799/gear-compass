import type { Content, GearData, Item, Setup, Skill, Slot, Source } from '../types';
import { checkReqs } from './scoring';

/** Ordered best → worst. */
export const READINESS = ['overgeared', 'well', 'ready', 'under', 'not'] as const;
export type Readiness = (typeof READINESS)[number];

export const READINESS_LABEL: Record<Readiness, string> = {
  overgeared: 'Overgeared', well: 'Well geared', ready: 'Ready', under: 'Undergeared', not: 'Not ready',
};

/** Credit for owning a tier-N item in a slot (tier 1 = best-in-slot). */
const OWNED_TIER_CREDIT = [1, 0.75, 0.55, 0.4, 0.3];
/** The weapon decides most fights, so it counts as much as three armour slots. */
const WEAPON_WEIGHT = 3;

export interface SetupReadiness {
  setup: Setup;
  level: Readiness;
  /** Weighted gear quality 0-1 (1 = best-in-slot everywhere) */
  quality: number;
  /** Fraction of non-weapon slots where the player owns any listed item */
  coverage: number;
  /** Slots where the player owns nothing listed */
  missing: Slot[];
}

export interface ContentReadiness {
  content: Content;
  level: Readiness;
  /** The setup the player is best equipped for (for raids: the median room) */
  best: SetupReadiness;
  /** Hard blockers, e.g. "Requires 87 Slayer (you: 60)" */
  blockers: string[];
  /** Soft requirements we can't check, e.g. quests */
  notes: string[];
}

const rank = (r: Readiness) => READINESS.indexOf(r);

const MIN_FULL_SLOTS = 5;
const slotCount = (s: Setup) =>
  Object.entries(s.slots).filter(([slot, tiers]) => slot !== 'special' && tiers!.some(t => t.length)).length;

export function setupReadiness(setup: Setup, owned: Set<string>, data: GearData, levels: Partial<Record<Skill, number>>): SetupReadiness {
  let weighted = 0, totalWeight = 0, covered = 0, other = 0;
  let hasWeapon = !setup.slots.weapon;
  const missing: Slot[] = [];

  for (const [slot, tiers] of Object.entries(setup.slots) as [Slot, string[][]][]) {
    if (slot === 'special' || !tiers.some(t => t.length)) continue;
    // Best tier where the player owns something they can actually equip.
    const tier = tiers.findIndex(names => names.some(n => owned.has(n) && data.items[n] && checkReqs(data.items[n], levels).ok));
    const w = slot === 'weapon' ? WEAPON_WEIGHT : 1;
    totalWeight += w;
    if (tier >= 0) weighted += w * OWNED_TIER_CREDIT[tier];
    else missing.push(slot);
    if (slot === 'weapon') hasWeapon = tier >= 0;
    else { other++; if (tier >= 0) covered++; }
  }

  const quality = totalWeight ? weighted / totalWeight : 0;
  const coverage = other ? covered / other : 1;
  const level: Readiness = !hasWeapon ? 'not'
    : quality >= 0.9 ? 'overgeared'
    : quality >= 0.7 ? 'well'
    : coverage >= 0.5 ? 'ready'
    : 'under';
  return { setup, level, quality, coverage, missing };
}

export function computeReadiness(data: GearData, ownedList: string[], levels: Partial<Record<Skill, number>>): Map<string, ContentReadiness> {
  const owned = new Set(ownedList);
  const out = new Map<string, ContentReadiness>();
  for (const content of data.content) {
    const all = content.setups.map(s => setupReadiness(s, owned, data, levels));
    // Partial tables (a phase's weapon swap, a 2-slot room note) are trivially "complete"; judge full loadouts.
    const full = all.filter(r => slotCount(r.setup) >= MIN_FULL_SLOTS);
    // Armour-only tables (e.g. "Moons of Peril armour") say nothing about the weapon, so they can't
    // vouch for readiness on their own; use them only when no setup lists a weapon.
    const pool = full.length ? full : all;
    const armed = pool.filter(r => r.setup.slots.weapon?.some(t => t.length));
    const setups = (armed.length ? armed : pool)
      .sort((a, b) => rank(a.level) - rank(b.level) || b.quality - a.quality);
    // A raid is only as doable as its typical room, so use the median room; elsewhere pick the best-suited setup.
    const best = content.category === 'raid' ? setups[Math.floor(setups.length / 2)] : setups[0];
    // If the judged setup is armour-only, the weapon comes from the content's other (weapon) tables.
    let gearLevel = best.level;
    if (!best.setup.slots.weapon?.some(t => t.length)) {
      const weapons = content.setups.flatMap(s => s.slots.weapon ?? []).flat();
      const hasWeapon = weapons.some(n => owned.has(n) && data.items[n] && checkReqs(data.items[n], levels).ok);
      if (weapons.length && !hasWeapon) gearLevel = 'not';
    }
    const blockers: string[] = [];
    if (content.slayerLevel && levels.slayer != null && levels.slayer < content.slayerLevel) {
      blockers.push(`Requires ${content.slayerLevel} Slayer (you: ${levels.slayer})`);
    }
    const notes = content.quests.length ? [`Requires ${content.quests.join(', ')}`] : [];
    out.set(content.id, { content, best, blockers, notes, level: blockers.length ? 'not' : gearLevel });
  }
  return out;
}

/** At least "Ready": the player can realistically farm it. */
export const canFarm = (r: ContentReadiness | undefined) => !!r && rank(r.level) <= rank('ready');

/** The most likely source of `item` that the player is ready to farm, if any. */
export function farmableSource(item: Item, readiness: Map<string, ContentReadiness>): Source | null {
  return item.sources.find(s => s.contentId && canFarm(readiness.get(s.contentId))) ?? null;
}
