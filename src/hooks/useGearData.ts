import { useEffect, useState } from 'react';
import type { GearData } from '../types';

export function useGearData() {
  const [data, setData] = useState<GearData | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/gear.json`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch(e => setError(String(e.message ?? e)));
  }, []);
  return { data, error };
}
