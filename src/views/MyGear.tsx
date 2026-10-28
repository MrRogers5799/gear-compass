import { useMemo, useState } from 'react';
import { useGear } from '../hooks/Gear';
import { useUserData } from '../hooks/UserData';
import { checkReqs } from '../lib/scoring';
import { canFarm, farmableSource, READINESS } from '../lib/readiness';
import { formatGp, imageUrl } from '../lib/wiki';
import { GettingStarted, ItemName, LockBadge, OwnWant, PageHeader, ReadinessBadge } from '../components/ui';
import type { Item, Source } from '../types';

/** Only suggest items recommended in a reasonable number of places, so one-boss niche gear doesn't dominate. */
const MIN_USES = 3;

const ownedKey = (item: Item) => `${item.slot}:${item.style === 'mixed' ? 'all' : item.style}`;

export function MyGear() {
  const { data, scores, price, readiness, iron } = useGear();
  const { data: user } = useUserData();
  const [tab, setTab] = useState<'farm' | 'buy' | 'reach' | 'unlock' | null>(null);

  const { buys, unlocks, farms, reach, bestOwned } = useMemo(() => {
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
    // Upgrades that drop from content the player is already geared for.
    const farms = candidates
      .map(c => ({ ...c, src: farmableSource(c.s.item, readiness) }))
      .filter(c => c.src)
      .sort((a, b) => b.gain - a.gain)
      .slice(0, iron ? 12 : 8);
    // Irons: upgrades from content they're not quite geared for yet — the next goals after "Farm next".
    const reach = iron ? candidates
      .filter(c => !c.s.item.sources.some(x => x.contentId && canFarm(readiness.get(x.contentId))))
      .map(c => ({ ...c, src: c.s.item.sources.find(x => x.contentId && readiness.get(x.contentId)?.level === 'under') }))
      .filter(c => c.src)
      .sort((a, b) => b.gain - a.gain)
      .slice(0, 10) : [];
    return { buys, unlocks, farms, reach, bestOwned };
  }, [scores, user.owned, user.levels, user.budget, price, readiness, iron]);

  const readyGroups = READINESS.filter(l => l !== 'not' && l !== 'under')
    .map(level => ({ level, list: [...readiness.values()].filter(r => r.level === level).map(r => r.content) }))
    .filter(g => g.list.length);
  const prayersToUnlock = data.prayers
    .filter(p => p.unlock && !user.prayers.includes(p.name))
    .sort((a, b) => b.usedAt.length - a.usedAt.length)
    .slice(0, 4);

  const wanted = user.wanted.map(n => data.items[n]).filter(Boolean);
  const wishlistCost = wanted.reduce((sum, i) => sum + (price(i.geId) ?? 0), 0);
  const owned = user.owned.map(n => data.items[n]).filter(Boolean)
    .sort((a, b) => a.slot.localeCompare(b.slot) || a.name.localeCompare(b.name));

  const Line = ({ item, extra }: { item: Item; extra?: React.ReactNode }) => (
    <li>
      <ItemName item={item} showSlot />
      <span className="grow" />
      {extra}
    </li>
  );

  const readyCount = [...readiness.values()].filter(r => canFarm(r)).length;
  const tabs = iron
    ? [['farm', `Farm next (${farms.length})`], ['reach', `Almost farmable (${reach.length})`], ['unlock', `Unlocks (${unlocks.length})`]] as const
    : [['farm', `Farm next (${farms.length})`], ['buy', `Buy (${buys.length})`], ['unlock', `Unlocks (${unlocks.length})`]] as const;
  const counts = { farm: farms.length, buy: buys.length, reach: reach.length, unlock: unlocks.length };
  // Until the player picks a tab, open the first one that has something in it.
  const activeTab = tabs.some(([t]) => t === tab) ? tab! : tabs.find(([t]) => counts[t] > 0)?.[0] ?? 'farm';

  return (
    <section>
      <PageHeader title="My gear" subtitle="What to go after next, based on the gear you own and your levels." />
      <GettingStarted />
      <div className="tiles">
        <a className="tile" href="#/content"><b>{readyCount}</b><span>bosses &amp; tasks you're ready for</span></a>
        <div className="tile"><b>{farms.length}</b><span>upgrades you can farm now</span></div>
        <div className="tile"><b>{owned.length}</b><span>items owned</span></div>
        <div className="tile"><b>{wanted.length}</b><span>on your wishlist{!iron && wanted.length > 0 ? ` · ${formatGp(wishlistCost)}` : ''}</span></div>
      </div>

      <div className="grid2">
        <div className="card pad">
          <h2 className="card-title">Upgrades</h2>
          <div className="tabs" role="tablist">
            {tabs.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={activeTab === id} className={'tab' + (activeTab === id ? ' on' : '')} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </div>
          {activeTab === 'farm' && <>
            <p className="muted small">Drops from bosses, raids or Slayer tasks you're already geared for. Biggest improvement first.</p>
            <ul className="list">
              {farms.map(({ s, gain, src }) => <Line key={s.item.name} item={s.item} extra={<SourceHint gain={gain} src={src!} />} />)}
              {!farms.length && <li className="muted">
                {user.owned.length ? "Nothing yet. Upgrades from content you're ready for will show here." : 'Mark the gear you own to see what you can farm.'}
              </li>}
            </ul>
          </>}
          {activeTab === 'reach' && <>
            <p className="muted small">Upgrades from content you're Undergeared for. A few more upgrades and these open up.</p>
            <ul className="list">
              {reach.map(({ s, gain, src }) => <Line key={s.item.name} item={s.item} extra={<SourceHint gain={gain} src={src!} />} />)}
              {!reach.length && <li className="muted">Nothing here right now.</li>}
            </ul>
          </>}
          {activeTab === 'buy' && <>
            <p className="muted small">
              The biggest tradeable upgrades (same slot and combat style) you can equip and afford.
              {user.budget != null ? ` Capped at your ${formatGp(user.budget)} budget.` : <> <a href="#/settings">Set a budget</a> to cap these.</>}
            </p>
            <ul className="list">
              {buys.map(({ s, gain, p }) => <Line key={s.item.name} item={s.item} extra={<span className="muted small">+{gain} · {formatGp(p)}</span>} />)}
              {!buys.length && <li className="muted">Nothing found. Try raising your budget.</li>}
            </ul>
          </>}
          {activeTab === 'unlock' && <>
            <p className="muted small">Untradeable gear earned through quests, minigames or Slayer, and often the best early upgrades.</p>
            <ul className="list">
              {unlocks.map(({ s, gain }) => <Line key={s.item.name} item={s.item} extra={<span className="muted small">+{gain}</span>} />)}
              {!unlocks.length && <li className="muted">Nothing here right now.</li>}
            </ul>
          </>}
          {Object.keys(user.levels).length === 0 && (
            <p className="muted small"><a href="#/settings">Add your levels</a> so suggestions skip gear you can't equip yet.</p>
          )}
        </div>

        <div className="stack">
          <div className="card pad">
            <h2 className="card-title">Where you're ready</h2>
            {readyGroups.map(g => (
              <details key={g.level} className="ready-group" open={g.list.length <= 8}>
                <summary><ReadinessBadge level={g.level} /> <span className="muted small">{g.list.length}</span></summary>
                <p className="ready-list">
                  {g.list.map((c, i) => <span key={c.id}>{i > 0 && ', '}<a href={`#/content/${c.id}`}>{c.name}</a></span>)}
                </p>
              </details>
            ))}
            {!readyGroups.length && <p className="muted small">Nothing yet. Mark the gear you own and this fills in.</p>}
          </div>

          {prayersToUnlock.length > 0 && (
            <div className="card pad">
              <h2 className="card-title">Prayers to unlock</h2>
              <ul className="list">
                {prayersToUnlock.map(p => (
                  <li key={p.name}>
                    <a className="item-name" href="#/prayers"><img className="icon" src={imageUrl(p.image)} alt="" width={24} height={24} />{p.name}</a>
                    <LockBadge item={p} />
                    <span className="grow" />
                    <span className="muted small">used at {p.usedAt.length}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="card pad">
            <h2 className="card-title">Wishlist</h2>
            <ul className="list">
              {wanted.map(i => (
                <Line key={i.name} item={i} extra={<><LockBadge item={i} />{!iron && <span className="muted small">{formatGp(price(i.geId))}</span>}<OwnWant name={i.name} /></>} />
              ))}
              {!wanted.length && <li className="muted small">Mark items as <b>Want</b> to plan your next goals.</li>}
            </ul>
          </div>

          <details className="card pad" open={owned.length <= 12}>
            <summary className="card-title">Owned <span className="muted small">{owned.length}</span></summary>
            <ul className="list">
              {owned.map(i => {
                const s = scores.get(i.name);
                // Only flag the exception: owned items outclassed by something else you own.
                const spare = s != null && (bestOwned.get(ownedKey(i)) ?? 0) > s.score;
                return <Line key={i.name} item={i} extra={<>{spare && <span className="muted small" title="You own something better for this slot and style">spare</span>}<OwnWant name={i.name} /></>} />;
              })}
              {!owned.length && <li className="muted small">Mark items as <b>Own</b> on the Rankings or Bosses &amp; Slayer pages.</li>}
            </ul>
          </details>
        </div>
      </div>
    </section>
  );
}

function SourceHint({ gain, src }: { gain: number; src: Source }) {
  const { contentById } = useGear();
  return (
    <span className="muted small">
      +{gain} · <a href={`#/content/${src.contentId}`}>{contentById.get(src.contentId!)?.name ?? src.from}</a>
      {' '}{src.rate ?? ''}{src.via && ` (${src.via})`}
    </span>
  );
}
