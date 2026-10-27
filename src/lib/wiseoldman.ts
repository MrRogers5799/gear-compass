import type { Skill } from '../types';

const API = 'https://api.wiseoldman.net/v2/players/';
const SKILLS: Skill[] = ['attack', 'strength', 'defence', 'ranged', 'magic', 'prayer', 'hitpoints', 'slayer'];

interface WomPlayer {
  displayName: string;
  latestSnapshot: { data: { skills: Record<string, { level: number }> } } | null;
}

/**
 * Fetch combat levels for an OSRS name from Wise Old Man.
 * `refresh` asks WOM to re-pull from the official hiscores first (also registers new players).
 */
export async function fetchLevels(rsn: string, refresh = false): Promise<{ name: string; levels: Partial<Record<Skill, number>> }> {
  const url = API + encodeURIComponent(rsn.trim());
  let res = await fetch(url, refresh ? { method: 'POST' } : undefined);
  if (!refresh && res.status === 404) res = await fetch(url, { method: 'POST' });
  if (res.status === 429) throw new Error('Wise Old Man rate limit hit, try again in a minute.');
  if (!res.ok) throw new Error(res.status === 400 || res.status === 404
    ? `Couldn't find "${rsn}" on the hiscores.`
    : `Wise Old Man error (${res.status}).`);
  const player = (await res.json()) as WomPlayer;
  const skills = player.latestSnapshot?.data.skills;
  if (!skills) throw new Error('No hiscores data for that player yet.');
  const levels: Partial<Record<Skill, number>> = {};
  for (const s of SKILLS) if (skills[s]) levels[s] = skills[s].level;
  return { name: player.displayName, levels };
}
