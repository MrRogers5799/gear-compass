import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { DEFAULT_WEIGHTS, type Weights } from '../lib/scoring';
import type { Skill } from '../types';

export interface UserData {
  owned: string[];
  wanted: string[];
  rsn: string;
  levels: Partial<Record<Skill, number>>;
  weights: Weights;
  /** Max GP for suggestions/filters; null = no limit */
  budget: number | null;
  /** Hide items whose level requirements aren't met */
  hideLocked: boolean;
}

const EMPTY: UserData = { owned: [], wanted: [], rsn: '', levels: {}, weights: DEFAULT_WEIGHTS, budget: null, hideLocked: false };
const LOCAL_KEY = 'gear-compass:v1';

function loadLocal(): UserData {
  try {
    const saved = JSON.parse(localStorage.getItem(LOCAL_KEY) ?? 'null');
    if (saved) return { ...EMPTY, ...saved, weights: { ...DEFAULT_WEIGHTS, ...saved.weights } };
  } catch { /* storage unavailable or corrupt */ }
  return EMPTY;
}

type SyncState = 'local' | 'loading' | 'synced' | 'saving' | 'error';

interface Ctx {
  data: UserData;
  update: (patch: Partial<UserData> | ((d: UserData) => Partial<UserData>)) => void;
  toggle: (list: 'owned' | 'wanted', name: string) => void;
  sync: SyncState;
}

const UserDataContext = createContext<Ctx | null>(null);

/**
 * Holds the player's lists and settings. Always mirrored to localStorage;
 * when signed in, also loaded from / saved to the Supabase `user_data` table.
 */
export function UserDataProvider({ user, children }: { user: User | null; children: ReactNode }) {
  const [data, setData] = useState<UserData>(loadLocal);
  const [sync, setSync] = useState<SyncState>('local');
  const remoteReady = useRef(false);

  // Load remote data on sign-in. A brand-new account adopts whatever was saved locally.
  useEffect(() => {
    remoteReady.current = false;
    if (!supabase || !user) { setSync('local'); return; }
    setSync('loading');
    supabase.from('user_data').select('data').eq('user_id', user.id).maybeSingle().then(({ data: row, error }) => {
      if (error) { setSync('error'); return; }
      if (row?.data) setData(d => ({ ...d, ...row.data, weights: { ...DEFAULT_WEIGHTS, ...row.data.weights } }));
      remoteReady.current = true;
      setSync('synced');
    });
  }, [user]);

  // Persist: localStorage immediately, Supabase debounced.
  useEffect(() => {
    try { localStorage.setItem(LOCAL_KEY, JSON.stringify(data)); } catch { /* ignore */ }
    if (!supabase || !user || !remoteReady.current) return;
    setSync('saving');
    const t = setTimeout(async () => {
      const { error } = await supabase!.from('user_data')
        .upsert({ user_id: user.id, data, updated_at: new Date().toISOString() });
      setSync(error ? 'error' : 'synced');
    }, 1000);
    return () => clearTimeout(t);
  }, [data, user]);

  const update: Ctx['update'] = patch => setData(d => ({ ...d, ...(typeof patch === 'function' ? patch(d) : patch) }));
  const toggle: Ctx['toggle'] = (list, name) =>
    update(d => ({ [list]: d[list].includes(name) ? d[list].filter(n => n !== name) : [...d[list], name] }));

  return <UserDataContext.Provider value={{ data, update, toggle, sync }}>{children}</UserDataContext.Provider>;
}

export function useUserData() {
  const ctx = useContext(UserDataContext);
  if (!ctx) throw new Error('useUserData outside UserDataProvider');
  return ctx;
}
