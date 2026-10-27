export const WIKI = 'https://oldschool.runescape.wiki/';

const underscore = (s: string) => encodeURIComponent(s.replace(/ /g, '_'));

export const imageUrl = (file: string) => `${WIKI}images/${underscore(file)}`;
export const pageUrl = (page: string) => `${WIKI}w/${underscore(page)}`;

/** 1234567 -> "1.2m" */
export function formatGp(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'b';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'm';
  if (n >= 1e3) return Math.round(n / 1e3) + 'k';
  return String(n);
}

/** "10m" / "500k" / "1.5b" / "25000" -> gp, or null if blank/invalid */
export function parseGp(s: string): number | null {
  const m = s.trim().toLowerCase().replace(/,/g, '').match(/^(\d+(?:\.\d+)?)\s*([kmb]?)$/);
  if (!m) return null;
  const mult = { '': 1, k: 1e3, m: 1e6, b: 1e9 }[m[2] as '' | 'k' | 'm' | 'b'];
  return Math.round(parseFloat(m[1]) * mult);
}

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
