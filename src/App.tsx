import { useCallback, useMemo, useState } from 'react';
import { useGearData } from './hooks/useGearData';
import { usePrices } from './hooks/usePrices';
import { useRoute } from './hooks/useRoute';
import { useAuth } from './hooks/useAuth';
import { ACCOUNT_LABEL, UserDataProvider, isIron, useUserData } from './hooks/UserData';
import { GearContext } from './hooks/Gear';
import { computeScores } from './lib/scoring';
import { computeReadiness } from './lib/readiness';
import { WIKI } from './lib/wiki';
import { ItemDrawer } from './components/ItemDrawer';
import { Rankings } from './views/Rankings';
import { ContentView } from './views/ContentView';
import { MyGear } from './views/MyGear';
import { Settings } from './views/Settings';
import { Prayers } from './views/Prayers';
import type { GearData } from './types';

const NAV = [
  ['rankings', 'Rankings'],
  ['content', 'Bosses & Slayer'],
  ['prayers', 'Prayers'],
  ['mine', 'My gear'],
  ['settings', 'Settings'],
] as const;

export default function App() {
  const { data, error } = useGearData();
  const auth = useAuth();

  if (error) return <p className="pad">Couldn't load gear data: {error}</p>;
  if (!data || !auth.ready) return <p className="pad muted">Loading…</p>;
  return (
    <UserDataProvider userId={auth.user?.id ?? null}>
      <Shell data={data} auth={auth} />
    </UserDataProvider>
  );
}

function Shell({ data, auth }: { data: GearData; auth: ReturnType<typeof useAuth> }) {
  const [view = 'rankings', ...params] = useRoute();
  const { data: user, sync, flush } = useUserData();
  const price = usePrices();
  const [openName, setOpenName] = useState<string | null>(null);
  const closeItem = useCallback(() => setOpenName(null), []);

  const scores = useMemo(() => computeScores(data, user.weights), [data, user.weights]);
  const contentById = useMemo(() => new Map(data.content.map(c => [c.id, c])), [data]);
  const readiness = useMemo(() => computeReadiness(data, user.owned, user.levels), [data, user.owned, user.levels]);
  const iron = isIron(user.accountType);
  const ctx = { data, scores, contentById, readiness, price, iron, openItem: setOpenName };

  return (
    <GearContext.Provider value={ctx}>
      <header>
        <a className="brand" href="#/">⚔ Gear Compass</a>
        <nav>
          {NAV.map(([id, label]) => (
            <a key={id} href={`#/${id}`} className={view === id ? 'on' : ''}>{label}</a>
          ))}
        </nav>
        <span className="grow" />
        <div className="account">
          {iron && <a className="iron-badge" href="#/settings" title="Account type (change in Settings)">⛓ {ACCOUNT_LABEL[user.accountType]}</a>}
          {!auth.enabled && <span className="muted small" title="Supabase isn't configured for this build">Saved in this browser</span>}
          {auth.enabled && !auth.user && <button className="btn discord" onClick={auth.signIn}>Sign in with Discord</button>}
          {auth.user && (
            <>
              <span className="small">{auth.displayName}</span>
              <span className={`sync ${sync}`} title={`Sync: ${sync}`} />
              <button className="btn" onClick={async () => { await flush(); await auth.signOut(); }}>Sign out</button>
            </>
          )}
        </div>
      </header>
      <main>
        {view === 'content' ? <ContentView id={params[0]} setupIndex={Number(params[1] ?? 0)} />
          : view === 'mine' ? <MyGear />
          : view === 'prayers' ? <Prayers />
          : view === 'settings' ? <Settings />
          : <Rankings />}
      </main>
      <ItemDrawer name={openName} onClose={closeItem} />
      <footer>
        Data from the <a href={WIKI} target="_blank" rel="noopener">Old School RuneScape Wiki</a> (CC BY-NC-SA 3.0),
        snapshot {data.generated}. Prices from the wiki's real-time prices API, levels from Wise Old Man.
        Not affiliated with Jagex. RuneScape is a trademark of Jagex Ltd.
      </footer>
    </GearContext.Provider>
  );
}
