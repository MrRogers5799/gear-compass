import { useMemo } from 'react';
import { useGear } from '../hooks/Gear';
import { useUserData } from '../hooks/UserData';
import { checkReqs, type Scored } from '../lib/scoring';
import { formatGp } from '../lib/wiki';
import { ItemName, LockBadge, OwnWant } from '../components/ui';
import type { Item } from '../types';

/** Only suggest items recommended in a reasonable number of places, so one-boss niche gear doesn't dominate. */
const MIN_USES = 3;

const ownedKey = (item: Item) => `${item.slot}:${item.style === 'mixed' ? 'all' : item.style}`;

export function MyGear() {
  const { data, scores, price } = useGear();
  const { data: user } = useUserData();

  const { buys, unlocks, bestOwned } = useMemo(() => {
    // Best owned score per slot+style, so a whip doesn't make every ranged weapon look like a downgrade.
    const bestOwned = new Map<string, number>();
    for (const n of user.owned) {
      const s = scores.get(n);
      if (s) bestOwned.set(ownedKey(s.item), Math.max(bestOwned.get(ownedKey(s.item)) ?? 0, s.score));
    }
    const baseline = (item: Item) => item.style === 'all' || item.style === 'mixed'
      ? Math.max(0, ...[...bestOwned].filter(([k]) => k.startsWith(item.slot + ':')).map(([, v]) => v))
      : Math.max(bestOwned.get(ownedKey(item)) ?? 0, bestOwned.get(`${item.slot}:all`) ?? 0);

    const candidates = [...scores.values()]
      // Ammo is excluded: prices are per arrow/bolt, which makes it look like a free upgrade.
      .filter(s => !['special', 'ammo'].includes(s.item.slot) && s.uses >= MIN_USES && !user.owned.includes(s.item.name))
      .filter(s => checkReqs(s.item, user.levels).ok)
      .map(s => ({ s, gain: s.score - baseline(s.item), p: price(s.item.geId) }))
      .filter(c => c.gain > 0);

    // Tradeables within budget: biggest improvement first, cheaper first on ties.
    const buys = candidates
      .filter(c => c.p != null && (user.budget == null || c.p <= user.budget))
      .sort((a, b) => b.gain - a.gain || a.p! - b.p!)
      .slice(0, 12);
    // Untradeables (Fire cape, Barrows gloves, Slayer helm...) are earned, not bought.
    const unlocks = candidates
      .filter(c => !c.s.item.tradeable)
      .sort((a, b) => b.gain - a.gain)
      .slice(0, 10);
    return { buys, unlocks, bestOwned };
  }, [scores, user.owned, user.levels, user.budget, price]);

  const wanted = user.wanted.map(n => data.items[n]).filter(Boolean);
  const wishlistCost = wanted.reduce((sum, i) => sum + (price(i.geId) ?? 0), 0);
  const owned = user.owned.map(n => data.items[n]).filter(Boolean)
    .sort((a, b) => a.slot.localeCompare(b.slot) || a.name.localeCompare(b.name));

  const Line = ({ s, extra }: { s: Scored; extra?: React.ReactNode }) => (
    <li>
      <ItemName item={s.item} showSlot />
      <span className="grow" />
      {extra}
    </li>
  );

  return (
    <section className="grid2">
      <div className="card pad">
        <h3>Best value buys</h3>
        <p className="muted small">
          The biggest tradeable upgrades over what you own (for the same slot and combat style) that you can equip and afford.
          {user.budget != null ? ` Capped at your ${formatGp(user.budget)} budget.` : ' Set a budget in Settings to cap these.'}
          {Object.keys(user.levels).length === 0 && ' Add your levels in Settings to hide gear you can\'t equip.'}
        </p>
        <ul className="list">
          {buys.map(({ s, gain, p }) => (
            <Line key={s.item.name} s={s} extra={<span className="muted small">+{gain} · {formatGp(p)}</span>} />
          ))}
          {!buys.length && <li className="muted">Nothing found. Try raising your budget.</li>}
        </ul>
        <h3>Unlocks to work toward</h3>
        <p className="muted small">Untradeable gear you earn through quests, minigames or Slayer, and often the best early upgrades.</p>
        <ul className="list">
          {unlocks.map(({ s, gain }) => <Line key={s.item.name} s={s} extra={<span className="muted small">+{gain}</span>} />)}
        </ul>
      </div>

      <div className="card pad">
        <h3>Wishlist {wanted.length > 0 && <span className="muted small">· {formatGp(wishlistCost)} total</span>}</h3>
        <ul className="list">
          {wanted.map(i => {
            const s = scores.get(i.name);
            return s ? <Line key={i.name} s={s} extra={<><LockBadge item={i} /><span className="muted small">{formatGp(price(i.geId))}</span><OwnWant name={i.name} /></>} /> : null;
          })}
          {!wanted.length && <li className="muted">Mark items as <b>Want</b> to plan your next goals.</li>}
        </ul>
        <h3>Owned</h3>
        <ul className="list">
          {owned.map(i => {
            const s = scores.get(i.name);
            const top = bestOwned.get(ownedKey(i)) === s?.score;
            return s ? <Line key={i.name} s={s} extra={<>{top && <span className="badge">best owned</span>}<OwnWant name={i.name} /></>} /> : null;
          })}
          {!owned.length && <li className="muted">Mark items as <b>Own</b> on the Rankings or Content pages.</li>}
        </ul>
      </div>
    </section>
  );
}
