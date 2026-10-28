import { useState } from 'react';
import { useGear } from '../hooks/Gear';
import { useUserData } from '../hooks/UserData';
import { capitalize, formatGp, imageUrl, pageUrl } from '../lib/wiki';
import { Chips, PageHeader, LockBadge, SourceList, StyleBadge } from '../components/ui';

const STYLES = ['all', 'melee', 'ranged', 'magic'] as const;

export function Prayers() {
  const { data, contentById, price, iron } = useGear();
  const { data: user, toggle } = useUserData();
  const [style, setStyle] = useState<(typeof STYLES)[number]>('all');

  const prayers = data.prayers
    .filter(p => style === 'all' || p.style === style || p.style === 'all')
    .sort((a, b) => b.usedAt.length - a.usedAt.length || (a.reqs.prayer ?? 0) - (b.reqs.prayer ?? 0));

  return (
    <section>
      <PageHeader title="Prayers" subtitle="Combat prayers ranked by how many strategy guides recommend them. Mark scroll and quest unlocks once you have them." />
      <div className="toolbar">
        <Chips options={STYLES} value={style} onChange={setStyle} />
      </div>
      <div className="prayer-grid">
        {prayers.map(p => {
          const unlocked = !p.unlock || user.prayers.includes(p.name);
          return (
            <article key={p.name} className="card pad prayer">
              <div className="prayer-head">
                <img className="icon" src={imageUrl(p.image)} alt="" width={32} height={32} />
                <div className="grow">
                  <h3><a href={pageUrl(p.name)} target="_blank" rel="noopener">{p.name}</a></h3>
                  <StyleBadge style={p.style} />{' '}
                  <span className="muted small">{Object.entries(p.reqs).map(([k, v]) => `${v} ${capitalize(k)}`).join(', ')}</span>
                </div>
                {p.unlock && (
                  <button className={'tg own' + (unlocked ? ' on' : '')} aria-pressed={unlocked} onClick={() => toggle('prayers', p.name)}>
                    {unlocked ? 'Unlocked' : 'Locked'}
                  </button>
                )}
              </div>
              <LockBadge item={p} />
              <p className="small">{p.effect}</p>
              {p.unlock && <p className="small"><b>Unlock:</b> {p.unlock}</p>}
              {p.scroll && !unlocked && (
                <details>
                  <summary className="small">
                    <img className="icon" src={imageUrl(p.scroll.image)} alt="" width={18} height={18} /> {p.scroll.name}
                    {p.scroll.geId != null && !iron && <> · GE {formatGp(price(p.scroll.geId))}</>}
                  </summary>
                  <SourceList sources={p.scroll.sources} />
                </details>
              )}
              <details>
                <summary className="small">Recommended at {p.usedAt.length} places</summary>
                <p className="small">
                  {p.usedAt.map(id => contentById.get(id)).filter(Boolean).map((c, i) => (
                    <span key={c!.id}>{i > 0 && ', '}<a href={`#/content/${c!.id}`}>{c!.name}</a></span>
                  ))}
                </p>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}
