import { createContext, useContext } from 'react';
import type { Content, GearData } from '../types';
import type { Scored } from '../lib/scoring';
import type { ContentReadiness } from '../lib/readiness';

export interface GearCtx {
  data: GearData;
  /** Scores under the player's current content weights */
  scores: Map<string, Scored>;
  contentById: Map<string, Content>;
  /** How well the player's owned gear fits each content (content id -> readiness) */
  readiness: Map<string, ContentReadiness>;
  price: (geId: number | null) => number | null;
  openItem: (name: string) => void;
}

export const GearContext = createContext<GearCtx | null>(null);

export function useGear() {
  const ctx = useContext(GearContext);
  if (!ctx) throw new Error('useGear outside GearContext');
  return ctx;
}
