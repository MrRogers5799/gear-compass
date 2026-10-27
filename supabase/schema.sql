-- Gear Compass: per-user saved data (owned/wanted lists, levels, settings).
-- Run once in the Supabase dashboard: SQL Editor -> New query -> paste -> Run.

create table if not exists public.user_data (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- Row Level Security: the anon key in the site is public, so these policies are
-- what stop one user reading or writing another user's row.
alter table public.user_data enable row level security;

create policy "read own data" on public.user_data
  for select using (auth.uid() = user_id);

create policy "insert own data" on public.user_data
  for insert with check (auth.uid() = user_id);

create policy "update own data" on public.user_data
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
