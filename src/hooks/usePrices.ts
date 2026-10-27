import { useEffect, useState } from 'react';

type PriceMap = Record<string, { high: number | null; low: number | null }>;

/** Live GE prices from the OSRS Wiki real-time prices API (one bulk request). */
export function usePrices() {
  const [prices, setPrices] = useState<PriceMap>({});
  useEffect(() => {
    fetch('https://prices.runescape.wiki/api/v1/osrs/latest')
      .then(r => r.json())
      .then(j => setPrices(j.data ?? {}))
      .catch(() => {});
  }, []);
  return (geId: number | null): number | null => {
    if (geId == null) return null;
    const p = prices[geId];
    return p ? (p.high ?? p.low) : null;
  };
}
