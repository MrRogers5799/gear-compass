import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { supabase } from '../lib/supabase';
import { DEFAULT_WEIGHTS, type Weights } from '../lib/scoring';
import type { Skill } from '../types';

export const ACCOUNT_TYPES = ['regular', 'ironman', 'hardcore', 'ultimate', 'group'] as const;
export type AccountType = (typeof ACCOUNT_TYPES)[number];
export const ACCOUNT_LABEL: Record<AccountType, string> = {
  regular: 'Regular', ironman: 'Ironman', hardcore: 'Hardcore Ironman', ultimate: 'Ultimate Ironman', group: 'Group Ironman',
};
/** Any ironman variant: can't use the GE, so gear has to be earned. */
export const isIron = (t: AccountType) => t !== 'regular';

export interface UserData {
  accountType: AccountType;
  owned: string[];
  wanted: string[];
  /** Prayers the player has unlocked (scroll read / quest done) */
  prayers: string[];
  rsn: string;
  levels: Partial<Record<Skill, number>>;
  weights: Weights;
  /** Max GP for suggestions/filters; null = no limit */
  budget: number | null;
  /** Hide items whose level requirements aren't met */
  hideLocked: boolean;
}

const EMPTY: UserData = { accountType: 'regular', owned: [], wanted: [], prayers: [], rsn: '', levels: {}, weights: DEFAULT_WEIGHTS, budget: null, hideLocked: false };

/** Signed-out data lives under the guest key; each signed-in account gets its own cache key. */
const GUEST_KEY = 'gear-compass:v1';
const accountKey = (id: string) => `${GUEST_KEY}:${id}`;
const SAVE_DELAY = 800;

/** `dirty` = changed locally since the last successful save to Supabase. */
interface Local { data: UserData; dirty: boolean }

const normalize = (d: Partial<UserData>): UserData => ({ ...EMPTY, ...d, weights: { ...DEFAULT_WEIGHTS, ...d.weights } });

function read(key: string): Local | null {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? 'null');
    if (!saved) return null;
    // v1 stored the bare UserData; treat it as unsaved so it gets merged into the account.
    return 'data' in saved && 'dirty' in saved ? { data: normalize(saved.data), dirty: saved.dirty } : { data: normalize(saved), dirty: true };
  } catch { return null; }
}
function write(key: string, value: Local) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}
function remove(key: string) {
  try { localStorage.removeItem(key); } catch { /* storage unavailable */ }
}

const isEmpty = (d: UserData) => !d.owned.length && !d.wanted.length && !d.prayers.length && !d.rsn && !Object.keys(d.levels).length;
const union = (a: string[], b: string[]) => [...new Set([...a, ...b])];

/** Unsaved local edits win for settings; lists are combined so nothing marked on either side is lost. */
function merge(remote: UserData, local: UserData): UserData {
  return {
    ...remote, ...local,
    owned: union(remote.owned, local.owned),
    wanted: union(remote.wanted, local.wanted),
    prayers: union(remote.prayers, local.prayers),
    levels: { ...remote.levels, ...local.levels },
    rsn: local.rsn || remote.rsn,
  };
}

type SyncState = 'local' | 'loading' | 'synced' | 'saving' | 'error';

interface Ctx {
  data: UserData;
  update: (patch: Partial<UserData> | ((d: UserData) => Partial<UserData>)) => void;
  toggle: (list: 'owned' | 'wanted' | 'prayers', name: string) => void;
  sync: SyncState;
  /** Save any pending changes now (call before signing out). */
  flush: () => Promise<void>;
}

const UserDataContext = createContext<Ctx | null>(null);

/**
 * Holds the player's lists and settings. Always mirrored to localStorage;
 * when signed in, also loaded from / saved to the Supabase `user_data` table.
 */
export function UserDataProvider({ userId, children }: { userId: string | null; children: ReactNode }) {
  // `owner` = the account this in-memory copy belongs to (null = guest), so a stale copy is never
  // written under another account's key during a switch.
  const [local, setLocal] = useState<Local & { owner: string | null }>(
    () => ({ ...(read(GUEST_KEY) ?? { data: EMPTY, dirty: false }), owner: null }));
  const [sync, setSync] = useState<SyncState>('local');
  const [retry, setRetry] = useState(0);
  const remoteReady = useRef(false);
  const latest = useRef(local);
  latest.current = local;

  const save = useCallback(async (snapshot: UserData) => {
    if (!supabase || !userId) return false;
    const { error } = await supabase.from('user_data')
      .upsert({ user_id: userId, data: snapshot, updated_at: new Date().toISOString() });
    if (error) { setSync('error'); return false; }
    // Only clear `dirty` if nothing changed while the request was in flight.
    setLocal(cur => (cur.data === snapshot ? { ...cur, dirty: false } : cur));
    setSync('synced');
    return true;
  }, [userId]);

  // Switching accounts (sign in / out / another user): load that account's data.
  useEffect(() => {
    remoteReady.current = false;
    if (!supabase || !userId) {
      setLocal({ ...(read(GUEST_KEY) ?? { data: EMPTY, dirty: false }), owner: null });
      setSync('local');
      return;
    }
    // Start from this account's cache so the UI isn't blank while loading. Anything marked while
    // signed out is folded in (and later merged with the server copy) rather than thrown away.
    const guest = read(GUEST_KEY);
    let start = read(accountKey(userId)) ?? { data: EMPTY, dirty: false };
    if (guest && !isEmpty(guest.data)) start = { data: merge(start.data, guest.data), dirty: true };
    setLocal({ ...start, owner: userId });
    setSync('loading');

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async (attempt: number) => {
      const { data: row, error } = await supabase!.from('user_data').select('data').eq('user_id', userId).maybeSingle();
      if (cancelled) return;
      if (error) {
        setSync('error');
        timer = setTimeout(() => load(attempt + 1), Math.min(30_000, 2_000 * 2 ** attempt));
        return;
      }
      const remote = row?.data ? normalize(row.data) : null;
      setLocal(cur => !remote ? { ...cur, dirty: true }          // new account: push what we have
        : cur.dirty ? { ...cur, data: merge(remote, cur.data), dirty: true }
        : { ...cur, data: remote, dirty: false });
      remove(GUEST_KEY); // now owned by this account; the next person to sign in here won't inherit it
      remoteReady.current = true;
      setSync('synced');
    };
    load(0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [userId]);

  // Persist: localStorage immediately, Supabase debounced while there are unsaved changes.
  useEffect(() => {
    const owner = supabase ? userId : null;
    if (local.owner !== owner) return; // mid-switch: this copy belongs to the previous account
    write(owner ? accountKey(owner) : GUEST_KEY, { data: local.data, dirty: local.dirty });
    if (!owner || !remoteReady.current || !local.dirty) return;
    setSync('saving');
    const t = setTimeout(async () => {
      if (!(await save(local.data))) setTimeout(() => setRetry(n => n + 1), 10_000);
    }, SAVE_DELAY);
    return () => clearTimeout(t);
  }, [local, userId, save, retry]);

  const flush = useCallback(async () => {
    if (userId && remoteReady.current && latest.current.dirty) await save(latest.current.data);
  }, [userId, save]);

  // Don't lose the last edit if the tab is hidden/closed inside the debounce window.
  useEffect(() => {
    const onHide = () => { if (document.visibilityState === 'hidden') flush(); };
    document.addEventListener('visibilitychange', onHide);
    return () => document.removeEventListener('visibilitychange', onHide);
  }, [flush]);

  const update: Ctx['update'] = patch =>
    setLocal(cur => ({ ...cur, data: { ...cur.data, ...(typeof patch === 'function' ? patch(cur.data) : patch) }, dirty: true }));
  const toggle: Ctx['toggle'] = (list, name) =>
    update(d => ({ [list]: d[list].includes(name) ? d[list].filter(n => n !== name) : [...d[list], name] }));

  return <UserDataContext.Provider value={{ data: local.data, update, toggle, sync, flush }}>{children}</UserDataContext.Provider>;
}

export function useUserData() {
  const ctx = useContext(UserDataContext);
  if (!ctx) throw new Error('useUserData outside UserDataProvider');
  return ctx;
}
