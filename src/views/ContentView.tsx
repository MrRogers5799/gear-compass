import { useMemo } from 'react';
import { useGear } from '../hooks/Gear';
import { useUserData } from '../hooks/UserData';
import { navigate } from '../hooks/useRoute';
import { checkReqs } from '../lib/scoring';
import { pageUrl } from '../lib/wiki';
import { Chips, ItemIcon } from '../components/ui';
import type { Category, Slot } from '../types';

const CATEGORIES = ['boss', 'raid', 'slayer', 'wilderness', 'minigame'] as const;
export const CATEGORY_LABEL: Record<Category, string> = {
  boss: 'Bosses', raid: 'Raids', slayer: 'Slayer', wilderness: 'Wilderness', minigame: 'Minigames',
};
const SLOT_ORDER: Slot[] = ['weapon', 'shield', 'head', 'body', 'legs', 'cape', 'neck', 'ammo', 'hands', 'feet', 'ring', 'special'];

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name);

export function ContentView({ id, setupIndex }: { id?: string; setupIndex: number }) {
  const { data, contentById, openItem } = useGear();
  const { data: user } = useUserData();
  const content = (id && contentById.get(id)) || data.content.find(c => c.id === 'vorkath') || data.content[0];
  const category = content.category;
  const list = useMemo(() => data.content.filter(c => c.category === category).sort(byName), [data, category]);
  const setup = content.setups[setupIndex] ?? content.setups[0];
  const owned = new Set(user.owned);

  const pickCategory = (c: Category) => {
    const first = data.content.filter(x => x.category === c).sort(byName)[0];
    if (first) navigate('content', first.id);
  };

  return (
    <section>
      <div className="toolbar">
        <Chips options={CATEGORIES} value={category} onChange={pickCategory} label={c => CATEGORY_LABEL[c]} />
      </div>
      <div className="toolbar">
        <select value={content.id} onChange={e => navigate('content', e.target.value)} aria-label="Choose content">
          {list.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <a href={pageUrl(content.page)} target="_blank" rel="noopener">Strategy guide on the wiki ↗</a>
      </div>
      {content.setups.length > 1 && (
        <div className="toolbar">
          <span className="label">Setup</span>
          <div className="chips">
            {content.setups.map((s, i) => (
              <button key={i} className={'chip' + (s === setup ? ' on' : '')} onClick={() => navigate('content', content.id, String(i))}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="card tier-grid">
        {SLOT_ORDER.filter(slot => setup.slots[slot]).map(slot => {
          // The first owned item met in tier order is the best one the player has for this slot.
          let bestFound = false;
          return (
            <div className="tier-row" key={slot}>
              <div className="slot-name">{slot}</div>
              <div className="tiers">
                {setup.slots[slot]!.map((names, t) => (
                  <div className="tier" key={t}>
                    <span className="t">T{t + 1}</span>
                    {names.map(n => {
                      const item = data.items[n];
                      if (!item) return null;
                      const has = owned.has(n);
                      const best = has && !bestFound;
                      if (best) bestFound = true;
                      const locked = !checkReqs(item, user.levels).ok;
                      return (
                        <button key={n} className={`pill${has ? ' owned' : ''}${best ? ' best' : ''}${locked ? ' locked' : ''}`}
                          onClick={() => openItem(n)} title={n + (locked ? ' (level requirements not met)' : '')}>
                          <ItemIcon item={item} size={22} />{n}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <p className="muted small">
        Tiers come straight from the wiki (tier 1 = most effective). Gear you own is outlined in green, and the best
        piece you own in each slot is ringed in gold. Faded items need higher levels than you have.
      </p>
    </section>
  );
}
