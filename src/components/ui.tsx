import type { ReactNode } from 'react';
import { imageUrl, capitalize } from '../lib/wiki';
import { checkReqs } from '../lib/scoring';
import { useUserData } from '../hooks/UserData';
import { useGear } from '../hooks/Gear';
import type { Item, Skill } from '../types';

const SKILL_ABBR: Record<Skill, string> = {
  attack: 'Att', strength: 'Str', defence: 'Def', ranged: 'Rng',
  magic: 'Mag', prayer: 'Pray', hitpoints: 'HP', slayer: 'Slay',
};

export function ItemIcon({ item, size = 32 }: { item: Pick<Item, 'image'>; size?: number }) {
  return <img className="icon" src={imageUrl(item.image)} alt="" loading="lazy" width={size} height={size} />;
}

export function Chips<T extends string>({ options, value, onChange, label }: {
  options: readonly T[]; value: T; onChange: (v: T) => void; label?: (v: T) => ReactNode;
}) {
  return (
    <div className="chips" role="group">
      {options.map(o => (
        <button key={o} className={'chip' + (o === value ? ' on' : '')} aria-pressed={o === value} onClick={() => onChange(o)}>
          {label ? label(o) : capitalize(o)}
        </button>
      ))}
    </div>
  );
}

export function StyleBadge({ style }: { style: string }) {
  return <span className={`badge s-${style}`}>{style === 'all' ? 'All styles' : style}</span>;
}

export function OwnWant({ name }: { name: string }) {
  const { data, toggle } = useUserData();
  const stop = (f: () => void) => (e: React.MouseEvent) => { e.stopPropagation(); f(); };
  const own = data.owned.includes(name), want = data.wanted.includes(name);
  return (
    <span className="toggles">
      <button className={'tg own' + (own ? ' on' : '')} aria-pressed={own} onClick={stop(() => toggle('owned', name))}>Own</button>
      <button className={'tg want' + (want ? ' on' : '')} aria-pressed={want} onClick={stop(() => toggle('wanted', name))}>Want</button>
    </span>
  );
}

/** Shows a lock with the missing levels if the player can't equip the item yet. */
export function LockBadge({ item }: { item: Item }) {
  const { data } = useUserData();
  const check = checkReqs(item, data.levels);
  if (check.ok) return null;
  const text = check.missing.map(m => `${m.need} ${capitalize(m.skill)} (you: ${m.have})`).join(', ');
  return <span className="lock" title={`Requires ${text}`}>🔒 {check.missing.map(m => `${m.need} ${SKILL_ABBR[m.skill]}`).join(' · ')}</span>;
}

export function ItemName({ item, showSlot }: { item: Item; showSlot?: boolean }) {
  const { openItem } = useGear();
  return (
    <button className="item-name" onClick={() => openItem(item.name)}>
      <ItemIcon item={item} />
      <span>{item.name}{showSlot && <span className="muted"> · {item.slot}</span>}</span>
    </button>
  );
}
