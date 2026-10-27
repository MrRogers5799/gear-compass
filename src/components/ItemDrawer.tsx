import { useEffect } from 'react';
import { useGear } from '../hooks/Gear';
import { capitalize, formatGp, pageUrl } from '../lib/wiki';
import { ItemIcon, LockBadge, OwnWant, SourceList, StyleBadge } from './ui';

const CATEGORY_LABEL: Record<string, string> = { boss: 'Boss', raid: 'Raid', slayer: 'Slayer', wilderness: 'Wildy', minigame: 'Minigame' };

export function ItemDrawer({ name, onClose }: { name: string | null; onClose: () => void }) {
  const { data, scores, price } = useGear();
  const item = name ? data.items[name] : null;
  const s = name ? scores.get(name) : undefined;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    addEventListener('keydown', onKey);
    addEventListener('hashchange', onClose);  // following a link out of the drawer
    return () => { removeEventListener('keydown', onKey); removeEventListener('hashchange', onClose); };
  }, [onClose]);

  return (
    <>
      <div className={'scrim' + (item ? ' open' : '')} onClick={onClose} />
      <aside className={'drawer' + (item ? ' open' : '')} aria-hidden={!item}>
        {item && (
          <>
            <button className="btn close" onClick={onClose} aria-label="Close">✕</button>
            <div className="drawer-head">
              <ItemIcon item={item} size={44} />
              <div>
                <h2>{item.name}</h2>
                <StyleBadge style={item.style} /> <span className="muted">{item.slot}{item.speed ? ` · speed ${item.speed}` : ''}{item.members ? '' : ' · F2P'}</span>
              </div>
            </div>
            <div className="stats">
              <div className="stat"><b>{s?.score ?? 0}</b><span>Relevance</span></div>
              <div className="stat"><b>{s?.bis ?? 0}</b><span>Best-in-slot at</span></div>
              <div className="stat"><b>{formatGp(price(item.geId))}</b><span>{item.tradeable ? 'GE price' : 'Untradeable'}</span></div>
            </div>
            <div className="row-gap">
              <OwnWant name={item.name} />
              <a href={pageUrl(item.name)} target="_blank" rel="noopener">Wiki ↗</a>
            </div>
            {(Object.keys(item.reqs).length > 0 || item.quests.length > 0) && (
              <div className="reqs">
                <h3>Requirements</h3>
                <p>
                  {Object.entries(item.reqs).map(([k, v]) => `${v} ${capitalize(k)}`).join(', ') || 'No skill requirements'}
                  {item.quests.length > 0 && <><br /><span className="muted">Quests: {item.quests.join(', ')}</span></>}
                </p>
                <LockBadge item={item} />
              </div>
            )}
            <h3>How to get it</h3>
            {item.tradeable && <p className="small">Buy on the Grand Exchange for <b>{formatGp(price(item.geId))}</b>, or:</p>}
            <SourceList sources={item.sources} />
            <h3>Recommended at {s?.uses ?? 0} places</h3>
            <ul className="used">
              {s?.usedAt.map(({ content, tier }) => (
                <li key={content.id}>
                  <a href={`#/content/${content.id}`}>{content.name}</a>
                  <span className="muted small">{CATEGORY_LABEL[content.category]}</span>
                  <span className={`tier-tag t${tier}`}>Tier {tier}</span>
                </li>
              ))}
            </ul>
            {!s && <p className="muted">Not recommended anywhere under your current content settings.</p>}
          </>
        )}
      </aside>
    </>
  );
}
