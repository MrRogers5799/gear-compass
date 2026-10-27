import { useEffect, useState } from 'react';
import { ACCOUNT_LABEL, ACCOUNT_TYPES, isIron, useUserData, type AccountType } from '../hooks/UserData';
import { fetchLevels } from '../lib/wiseoldman';
import { DEFAULT_WEIGHTS } from '../lib/scoring';
import { capitalize, formatGp, parseGp } from '../lib/wiki';
import { CATEGORY_LABEL } from './ContentView';
import type { Category, Skill } from '../types';

const SKILLS: Skill[] = ['attack', 'strength', 'defence', 'ranged', 'magic', 'prayer', 'hitpoints', 'slayer'];

export function Settings() {
  const { data, update } = useUserData();
  const [rsn, setRsn] = useState(data.rsn);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [budget, setBudget] = useState(data.budget == null ? '' : formatGp(data.budget));

  // Synced data can arrive after this page mounts; keep the text fields in step with it.
  useEffect(() => setRsn(data.rsn), [data.rsn]);
  useEffect(() => setBudget(data.budget == null ? '' : formatGp(data.budget)), [data.budget]);

  const importLevels = async (refresh: boolean) => {
    if (!rsn.trim()) return;
    setBusy(true);
    setStatus(refresh ? 'Asking Wise Old Man to update from the hiscores…' : 'Looking up…');
    try {
      const { name, levels, type } = await fetchLevels(rsn, refresh);
      // Group ironmen show as regular on the hiscores, so don't let that overwrite a manual "Group" choice.
      const keepGroup = type === 'regular' && data.accountType === 'group';
      const accountType: AccountType = type && !keepGroup ? type : data.accountType;
      update({ rsn: name, levels, accountType });
      setRsn(name);
      setStatus(`Imported levels for ${name} (${ACCOUNT_LABEL[accountType]}).`);
    } catch (e) {
      setStatus((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setLevel = (skill: Skill, v: string) => {
    const n = parseInt(v, 10);
    update(d => {
      const levels = { ...d.levels };
      if (Number.isFinite(n)) levels[skill] = Math.min(99, Math.max(1, n));
      else delete levels[skill];
      return { levels };
    });
  };

  const saveBudget = () => {
    const gp = budget.trim() ? parseGp(budget) : null;
    if (budget.trim() && gp == null) {  // unreadable input: put the saved value back rather than clearing it
      setBudget(data.budget == null ? '' : formatGp(data.budget));
      return;
    }
    if (gp !== data.budget) update({ budget: gp });
    setBudget(gp == null ? '' : formatGp(gp));
  };

  return (
    <section className="grid2">
      <div className="card pad">
        <h3>Your account</h3>
        <p className="muted small">Import combat levels from the hiscores through Wise Old Man, or type them in yourself.</p>
        <form className="row-gap" onSubmit={e => { e.preventDefault(); importLevels(false); }}>
          <input placeholder="OSRS username" value={rsn} onChange={e => setRsn(e.target.value)} maxLength={12} />
          <button className="btn primary" disabled={busy || !rsn.trim()}>Import</button>
          <button type="button" className="btn" disabled={busy || !rsn.trim()} onClick={() => importLevels(true)}
            title="Ask Wise Old Man to pull fresh data from the hiscores">Refresh</button>
        </form>
        {status && <p className="small">{status}</p>}
        <label className="row-gap">
          <span>Account type</span>
          <select value={data.accountType} onChange={e => update({ accountType: e.target.value as AccountType })}>
            {ACCOUNT_TYPES.map(t => <option key={t} value={t}>{ACCOUNT_LABEL[t]}</option>)}
          </select>
        </label>
        {isIron(data.accountType) && (
          <p className="muted small">Iron mode: GE prices and buying suggestions are hidden, and upgrades focus on drops you can farm.</p>
        )}
        <div className="levels">
          {SKILLS.map(s => (
            <label key={s}>
              <span>{capitalize(s)}</span>
              <input type="number" min={1} max={99} placeholder="?" value={data.levels[s] ?? ''} onChange={e => setLevel(s, e.target.value)} />
            </label>
          ))}
        </div>
      </div>

      <div className="card pad">
        <h3>What do you want to fight?</h3>
        <p className="muted small">
          Relevance only counts the content you care about. Set a category to 0 to ignore it, or raise it to focus on it.
        </p>
        <div className="weights">
          {(Object.keys(CATEGORY_LABEL) as Category[]).map(c => (
            <label key={c}>
              <span>{CATEGORY_LABEL[c]}</span>
              <input type="range" min={0} max={2} step={0.25} value={data.weights[c]}
                onChange={e => update(d => ({ weights: { ...d.weights, [c]: parseFloat(e.target.value) } }))} />
              <b>{data.weights[c] === 0 ? 'off' : `×${data.weights[c]}`}</b>
            </label>
          ))}
        </div>
        <button className="btn" onClick={() => update({ weights: DEFAULT_WEIGHTS })}>Reset to defaults</button>

        {!isIron(data.accountType) && <>
          <h3 style={{ marginTop: 20 }}>Budget</h3>
          <p className="muted small">Caps upgrade suggestions and the "Within budget" filter. Use values like 5m or 500k.</p>
          <form className="row-gap" onSubmit={e => { e.preventDefault(); saveBudget(); }}>
            <input placeholder="No limit" value={budget} onChange={e => setBudget(e.target.value)} onBlur={saveBudget} />
            <button className="btn primary">Save</button>
          </form>
        </>}
      </div>
    </section>
  );
}
