import type { Category, Content, GearData, Item, Skill, Slot } from '../types';

/** Weight of an appearance by tier: tier 1 (best-in-slot) counts fully, fallbacks much less. */
export const TIER_WEIGHT = [1, 0.6, 0.4, 0.25, 0.15];

export type Weights = Record<Category, number>;

export const DEFAULT_WEIGHTS: Weights = { boss: 1, raid: 0.5, slayer: 1, wilderness: 0.5, minigame: 0.5 };

export interface Scored {
  item: Item;
  /** 0-100, relative to the top item in the same slot */
  score: number;
  raw: number;
  /** Number of (enabled) content entries where it's tier 1 */
  bis: number;
  /** Number of (enabled) content entries recommending it at all */
  uses: number;
  avgTier: number;
  usedAt: { content: Content; tier: number }[];
}

export function computeScores(data: GearData, weights: Weights): Map<string, Scored> {
  const byId = new Map(data.content.map(c => [c.id, c]));
  const out = new Map<string, Scored>();
  const top = new Map<Slot, number>();

  for (const item of Object.values(data.items)) {
    let raw = 0, bis = 0, tierSum = 0;
    const usedAt: Scored['usedAt'] = [];
    for (const [cid, tier] of Object.entries(item.best)) {
      const content = byId.get(cid);
      const w = content ? weights[content.category] : 0;
      if (!content || !w) continue;
      raw += w * TIER_WEIGHT[tier - 1];
      if (tier === 1) bis++;
      tierSum += tier;
      usedAt.push({ content, tier });
    }
    if (!usedAt.length) continue;
    usedAt.sort((a, b) => a.tier - b.tier || a.content.name.localeCompare(b.content.name));
    out.set(item.name, { item, raw, score: 0, bis, uses: usedAt.length, avgTier: tierSum / usedAt.length, usedAt });
    top.set(item.slot, Math.max(top.get(item.slot) ?? 0, raw));
  }

  for (const s of out.values()) s.score = Math.round((100 * s.raw) / (top.get(s.item.slot) || 1));
  return out;
}

export interface ReqCheck {
  /** false only when we know the player's levels and one is too low */
  ok: boolean;
  missing: { skill: Skill; need: number; have: number }[];
}

export function checkReqs(item: Pick<Item, 'reqs'>, levels: Partial<Record<Skill, number>>): ReqCheck {
  const missing: ReqCheck['missing'] = [];
  for (const [skill, need] of Object.entries(item.reqs) as [Skill, number][]) {
    const have = levels[skill];
    if (have != null && have < need) missing.push({ skill, need, have });
  }
  return { ok: missing.length === 0, missing };
}
