import { useEffect, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(!supabase);

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { setUser(data.session?.user ?? null); setReady(true); });
    const { data } = supabase.auth.onAuthStateChange((_e, session) => setUser(session?.user ?? null));
    return () => data.subscription.unsubscribe();
  }, []);

  const signIn = () => supabase?.auth.signInWithOAuth({
    provider: 'discord',
    options: { redirectTo: location.origin + location.pathname },
  });
  const signOut = () => supabase?.auth.signOut();
  const displayName: string | null = user
    ? user.user_metadata?.custom_claims?.global_name ?? user.user_metadata?.full_name ?? user.user_metadata?.name ?? 'Signed in'
    : null;

  return { user, ready, enabled: !!supabase, signIn, signOut, displayName };
}
