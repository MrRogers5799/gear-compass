import { useState, type ReactNode } from 'react';
import { imageUrl, capitalize, pageUrl } from '../lib/wiki';
import { checkReqs } from '../lib/scoring';
import { READINESS_LABEL, type Readiness } from '../lib/readiness';
import { useUserData } from '../hooks/UserData';
import { useGear } from '../hooks/Gear';
import type { Item, Skill, Source } from '../types';

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

/** Shows a lock with the missing levels if the player can't equip the item (or use the prayer) yet. */
export function LockBadge({ item }: { item: Pick<Item, 'reqs'> }) {
  const { data } = useUserData();
  const check = checkReqs(item, data.levels);
  if (check.ok) return null;
  const text = check.missing.map(m => `${m.need} ${capitalize(m.skill)} (you: ${m.have})`).join(', ');
  return <span className="lock" title={`Requires ${text}`}>🔒 {check.missing.map(m => `${m.need} ${SKILL_ABBR[m.skill]}`).join(' · ')}</span>;
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p className="muted">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

const INTRO_KEY = 'gear-compass:intro-dismissed';

/** First-visit guide: shown until the player has set levels or marked gear, or dismisses it. */
export function GettingStarted() {
  const { data } = useUserData();
  const [dismissed, setDismissed] = useState(() => { try { return !!localStorage.getItem(INTRO_KEY); } catch { return false; } });
  const hasLevels = Object.keys(data.levels).length > 0;
  const hasGear = data.owned.length > 0;
  if (dismissed || (hasLevels && hasGear)) return null;
  const dismiss = () => { setDismissed(true); try { localStorage.setItem(INTRO_KEY, '1'); } catch { /* ignore */ } };
  return (
    <div className="card pad intro">
      <button className="btn close" onClick={dismiss} aria-label="Dismiss">✕</button>
      <h2 className="card-title">Getting started</h2>
      <ol>
        <li className={hasLevels ? 'done' : ''}><a href="#/settings">Import your levels</a> so gear you can't equip yet gets flagged.</li>
        <li className={hasGear ? 'done' : ''}>Mark the gear you <b>Own</b>, on <a href="#/rankings">Rankings</a> or a boss's page in <a href="#/content">Bosses &amp; Slayer</a>.</li>
        <li>Check <a href="#/mine">My gear</a> for what to farm or buy next.</li>
      </ol>
    </div>
  );
}

export function ReadinessBadge({ level }: { level: Readiness }) {
  return <span className={`ready r-${level}`}>{READINESS_LABEL[level]}</span>;
}

/** Where to get an item: each source with its drop rate and, for content we track, how ready the player is. */
export function SourceList({ sources }: { sources: Source[] }) {
  const { readiness } = useGear();
  if (!sources.length) return <p className="muted small">No drop or reward sources found on the wiki.</p>;
  return (
    <ul className="sources">
      {sources.map(s => {
        const r = s.contentId ? readiness.get(s.contentId) : undefined;
        return (
          <li key={s.from}>
            {s.contentId
              ? <a href={`#/content/${s.contentId}`}>{s.from}</a>
              : <a href={pageUrl(s.page)} target="_blank" rel="noopener">{s.from} ↗</a>}
            {s.via && <span className="muted small">({s.via})</span>}
            {s.kind !== 'drop' && <span className="muted small">{s.kind}</span>}
            <span className="grow" />
            {r && <ReadinessBadge level={r.level} />}
            <span className="rate">{s.rate ?? '—'}</span>
          </li>
        );
      })}
    </ul>
  );
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
