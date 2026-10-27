# Gear Compass

An OSRS gear-relevance guide for newer players. It ranks melee, ranged and magic gear by how often (and how highly)
the [OSRS Wiki](https://oldschool.runescape.wiki/) strategy guides recommend it across bosses, raids and Slayer.
Rankings take into account the player's levels, budget and the content they care about.

- **Rankings**: relevance score per slot/style, live GE prices, own/want tracking
- **Bosses & Slayer**: the wiki's tiered equipment table for each boss or task, with your gear highlighted
- **My gear**: best-value upgrades within budget, untradeable unlocks to work toward, wishlist
- **Settings**: import levels from Wise Old Man, weight content categories, set a budget
- **Accounts**: Discord sign-in (Supabase) syncs everything across devices; without it, data stays in the browser

## Development

```bash
npm install
npm run dev          # http://localhost:5173
npm run data         # re-pull public/data/gear.json from the wiki (Python 3, no deps)
npm run build        # type-check + production build into dist/
```

The app is a static Vite + React + TypeScript site. Gear data is pre-built into `public/data/gear.json` by
[scripts/build_data.py](scripts/build_data.py) (see [scripts/README.md](scripts/README.md)). The data contract is in
[src/types.ts](src/types.ts). Scoring happens in the browser ([src/lib/scoring.ts](src/lib/scoring.ts)), so it can
react to each player's settings.

## Deploying to GitHub Pages

1. Push this repo to GitHub (branch `main`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. The [workflow](.github/workflows/deploy.yml) builds and deploys on every push. Every Monday it also refreshes the wiki data
   (commits it if changed) and pings Supabase so the free project doesn't pause. Run it manually from the Actions tab
   any time.

The site works without Supabase. The sign-in button is replaced by "Saved in this browser".

## Setting up Discord sign-in (Supabase)

1. **Supabase**: create a free project at [supabase.com](https://supabase.com). In **SQL Editor**, run
   [supabase/schema.sql](supabase/schema.sql).
2. **Discord**: at [discord.com/developers/applications](https://discord.com/developers/applications), create an
   application. Under **OAuth2**, add the redirect `https://<project-ref>.supabase.co/auth/v1/callback` and copy the
   Client ID and Client Secret.
3. **Supabase → Authentication → Sign In / Providers → Discord**: enable it and paste the ID and secret.
4. **Supabase → Authentication → URL Configuration**:
   - Site URL: `https://<github-user>.github.io/<repo>/`
   - Redirect URLs: `https://<github-user>.github.io/<repo>/**` and `http://localhost:5173/**`
5. **GitHub → Settings → Secrets and variables → Actions → Variables**: add `VITE_SUPABASE_URL` and
   `VITE_SUPABASE_ANON_KEY`. Both are in Supabase under **Project Settings → API**. Use the anon/publishable key,
   **never** the service-role/secret key.
6. For local dev, copy `.env.example` to `.env.local` and fill in the same two values.

The anon key is public by design. The row-level security policies in `schema.sql` make sure each user can only read
and write their own row.

## Credits & licence

Gear data comes from the Old School RuneScape Wiki and is used under
[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/). This project must stay non-commercial.
Item images are hotlinked from the wiki. Prices come from the wiki's real-time prices API and player levels from
[Wise Old Man](https://wiseoldman.net). RuneScape is a trademark of Jagex Ltd. This project is not affiliated with Jagex.
