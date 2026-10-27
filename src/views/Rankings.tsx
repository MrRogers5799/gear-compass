import { useMemo, useState } from 'react';
import { useGear } from '../hooks/Gear';
import { useUserData } from '../hooks/UserData';
import { checkReqs } from '../lib/scoring';
import { formatGp } from '../lib/wiki';
import { Chips, ItemName, LockBadge, OwnWant, StyleBadge } from '../components/ui';
import type { Slot } from '../types';

const STYLES = ['all', 'melee', 'ranged', 'magic'] as const;
const SLOTS = ['all', 'weapon', 'head', 'body', 'legs', 'shield', 'cape', 'neck', 'ammo', 'hands', 'feet', 'ring', 'special'] as const;

export function Rankings() {
  const { scores, price } = useGear();
  const { data: user, update } = useUserData();
  const [style, setStyle] = useState<(typeof STYLES)[number]>('all');
  const [slot, setSlot] = useState<(typeof SLOTS)[number]>('weapon');
  const [q, setQ] = useState('');
  const [inBudget, setInBudget] = useState(false);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return [...scores.values()]
      .filter(s => slot === 'all' || s.item.slot === (slot as Slot))
      .filter(s => style === 'all' || s.item.style === style || s.item.style === 'all')
      .filter(s => !needle || s.item.name.toLowerCase().includes(needle))
      .filter(s => !user.hideLocked || checkReqs(s.item, user.levels).ok)
      .filter(s => {
        if (!inBudget || user.budget == null) return true;
        const p = price(s.item.geId);
        return p == null || p <= user.budget;
      })
      .sort((a, b) => b.score - a.score || b.uses - a.uses)
      .slice(0, 100);
  }, [scores, slot, style, q, user.hideLocked, user.levels, user.budget, inBudget, price]);

  return (
    <section>
      <div className="toolbar">
        <input type="search" placeholder="Search items…" value={q} onChange={e => setQ(e.target.value)} />
        <Chips options={STYLES} value={style} onChange={setStyle} />
      </div>
      <div className="toolbar">
        <span className="label">Slot</span>
        <Chips options={SLOTS} value={slot} onChange={setSlot} />
      </div>
      <div className="toolbar">
        <label className="check">
          <input type="checkbox" checked={user.hideLocked} onChange={e => update({ hideLocked: e.target.checked })} />
          Hide gear I can't equip yet
        </label>
        <label className="check" title={user.budget == null ? 'Set a budget in Settings' : undefined}>
          <input type="checkbox" checked={inBudget} disabled={user.budget == null} onChange={e => setInBudget(e.target.checked)} />
          Within budget{user.budget != null && ` (${formatGp(user.budget)})`}
        </label>
      </div>
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>Item</th><th className="hide-sm">Style</th><th>Relevance</th>
              <th className="num hide-sm" title="Places where it's tier 1">BiS at</th>
              <th className="num hide-sm" title="Places recommending it at all">Used at</th>
              <th className="num hide-sm">GE price</th><th />
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <tr key={s.item.name}>
                <td className="muted">{i + 1}</td>
                <td><ItemName item={s.item} showSlot={slot === 'all'} /><LockBadge item={s.item} /></td>
                <td className="hide-sm"><StyleBadge style={s.item.style} /></td>
                <td><div className="score"><div className="bar"><i style={{ width: `${s.score}%` }} /></div><b>{s.score}</b></div></td>
                <td className="num hide-sm">{s.bis}</td>
                <td className="num hide-sm">{s.uses}</td>
                <td className="num hide-sm">{s.item.tradeable ? formatGp(price(s.item.geId)) : <span className="muted">untradeable</span>}</td>
                <td><OwnWant name={s.item.name} /></td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={8} className="muted">No items match.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Relevance adds up the item's best tier at every boss, raid and Slayer task you've enabled in Settings
        (tier 1 = 1.0, 2 = 0.6, 3 = 0.4, 4 = 0.25, 5 = 0.15), times that category's weight, then scales so the
        top item in each slot is 100.
      </p>
    </section>
  );
}
