-- ═══════════════════════════════════════════════════════════════
-- JobPulse — Initial Schema Migration
-- Run this in: Supabase Dashboard → SQL Editor → Run
-- ═══════════════════════════════════════════════════════════════

-- Extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ─────────────────────────────────────────
-- USERS (mirrors auth.users)
-- ─────────────────────────────────────────
create table public.users (
  id uuid references auth.users(id) on delete cascade primary key,
  email text not null,
  telegram_chat_id bigint unique,
  notification_threshold int default 70 check (notification_threshold between 0 and 100),
  notification_frequency text default 'realtime' check (notification_frequency in ('realtime', 'daily', 'paused')),
  daily_digest_time time default '08:00',
  created_at timestamptz default now()
);

-- Auto-create user row on auth signup
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email);
  insert into public.user_profiles (user_id)
  values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ─────────────────────────────────────────
-- USER PROFILES
-- ─────────────────────────────────────────
create table public.user_profiles (
  user_id uuid references public.users(id) on delete cascade primary key,
  natural_language_description text,
  target_roles jsonb default '[]'::jsonb,
  skills jsonb default '[]'::jsonb,
  seniority_levels jsonb default '["internship","entry","junior"]'::jsonb,
  role_types jsonb default '["full-time","internship","contract"]'::jsonb,
  min_display_score int default 55,
  currency_preference text default 'usd_gbp_eur',
  show_senior boolean default false,
  show_unverified_remote boolean default true
);

-- ─────────────────────────────────────────
-- RESUMES
-- ─────────────────────────────────────────
create table public.resumes (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references public.users(id) on delete cascade,
  raw_text text,
  parsed_skills jsonb default '[]'::jsonb,
  parsed_experience_years float,
  storage_path text,
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────
-- JOB SOURCES
-- ─────────────────────────────────────────
create table public.job_sources (
  id uuid default uuid_generate_v4() primary key,
  name text not null,
  url text not null,
  source_type text not null check (source_type in ('api', 'rss', 'jina', 'company_page')),
  category text default 'General',
  is_library boolean default false,
  user_id uuid references public.users(id) on delete cascade,
  is_active boolean default true,
  health_status text default 'healthy' check (health_status in ('healthy','degraded','dead','low_quality')),
  consecutive_errors int default 0,
  last_fetched timestamptz,
  last_job_count int default 0,
  jobs_passing_filter_rate float default 0,
  created_at timestamptz default now()
);

-- Seed default library sources (pre-loaded, is_library=true, user_id=null)
insert into public.job_sources (name, url, source_type, category, is_library, user_id, is_active) values
  -- API sources (enabled by default)
  ('Remotive', 'https://remotive.com/api/remote-jobs', 'api', 'Aggregator', true, null, true),
  ('Himalayas', 'https://himalayas.app/jobs/api', 'api', 'Aggregator', true, null, true),
  ('Jobicy', 'https://jobicy.com/api/v2/remote-jobs', 'api', 'Aggregator', true, null, true),
  ('Arbeitnow', 'https://www.arbeitnow.com/api/job-board-api', 'api', 'Aggregator', true, null, true),
  ('RemoteOK', 'https://remoteok.com/api', 'api', 'Aggregator', true, null, true),
  ('Working Nomads', 'https://www.workingnomads.com/api/exposed_jobs/', 'api', 'General', true, null, true),
  -- RSS sources (enabled by default)
  ('We Work Remotely', 'https://weworkremotely.com/remote-jobs.rss', 'rss', 'General', true, null, true),
  ('Remote.co', 'https://remote.co/remote-jobs/feed/', 'rss', 'General', true, null, true),
  -- Jina sources (disabled by default — require scraping)
  ('Wellfound', 'https://wellfound.com/jobs/remote', 'jina', 'Startups', true, null, false),
  ('Built In', 'https://builtin.com/jobs/remote', 'jina', 'Tech', true, null, false),
  ('Jobspresso', 'https://jobspresso.co/', 'jina', 'General', true, null, false),
  ('JustRemote', 'https://justremote.co', 'jina', 'General', true, null, false),
  ('Daily Remote', 'https://dailyremote.com', 'jina', 'General', true, null, false),
  ('JobsCollider', 'https://jobscollider.com/remote-jobs', 'jina', 'Aggregator', true, null, false),
  ('Remote Index', 'https://remoteindex.co/', 'jina', 'Aggregator', true, null, false),
  ('Findwork', 'https://findwork.dev/', 'jina', 'Tech', true, null, false),
  ('Remote AI Jobs', 'https://www.moaijobs.com/remote-ai-jobs', 'jina', 'AI/Data', true, null, false),
  ('Remote Backend Jobs', 'https://www.remotebackendjobs.com/', 'jina', 'Backend', true, null, false),
  ('Remote Frontend Jobs', 'https://www.remotefrontendjobs.com/', 'jina', 'Frontend', true, null, false),
  ('Virtual Vocations', 'https://www.virtualvocations.com/', 'jina', 'General', true, null, false),
  ('NODESK', 'https://nodesk.co/remote-jobs/', 'jina', 'General', true, null, false),
  ('Real Work From Anywhere', 'https://www.realworkfromanywhere.com/', 'jina', 'Worldwide', true, null, false),
  ('HN Hiring', 'https://www.hnhiring.me/', 'jina', 'Tech', true, null, false),
  ('Career Vault', 'https://careervault.io/', 'jina', 'Aggregator', true, null, false),
  ('4 Day Week', 'https://4dayweek.io', 'jina', 'General', true, null, false),
  ('Dataaxy', 'https://dataaxy.com', 'jina', 'AI/Data', true, null, false),
  ('Freel', 'https://freel.ai', 'jina', 'AI/Data', true, null, false),
  ('Remote.io', 'https://www.remote.io/', 'jina', 'Aggregator', true, null, false),
  ('Authentic Jobs', 'https://authenticjobs.com/?search_location=remote', 'jina', 'Tech', true, null, false),
  ('Skip the Drive', 'https://www.skipthedrive.com/', 'jina', 'General', true, null, false);

-- ─────────────────────────────────────────
-- JOBS
-- ─────────────────────────────────────────
create table public.jobs (
  id uuid default uuid_generate_v4() primary key,
  source_id uuid references public.job_sources(id),
  external_id text,
  title text not null,
  company text not null,
  remote_type text default 'unknown',
  seniority text default 'unknown',
  role_type text default 'unknown',
  is_trainee boolean default false,
  description text,
  apply_url text,
  salary_range text,
  currency_signal text default 'unknown',
  tags jsonb default '[]'::jsonb,
  posted_at timestamptz,
  fetched_at timestamptz default now(),
  dedup_hash text unique
);
create index idx_jobs_dedup_hash on public.jobs(dedup_hash);
create index idx_jobs_fetched_at on public.jobs(fetched_at desc);
create index idx_jobs_source_id on public.jobs(source_id);

-- ─────────────────────────────────────────
-- JOB MATCHES
-- ─────────────────────────────────────────
create table public.job_matches (
  id uuid default uuid_generate_v4() primary key,
  job_id uuid references public.jobs(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  match_score int check (match_score between 0 and 100),
  match_reasons jsonb default '[]'::jsonb,
  disqualifiers jsonb default '[]'::jsonb,
  remote_verified boolean default false,
  seniority_verified boolean default false,
  status text default 'new' check (status in ('new','seen','saved','applied','rejected')),
  telegram_notified boolean default false,
  created_at timestamptz default now(),
  unique(job_id, user_id)
);
create index idx_job_matches_user_status on public.job_matches(user_id, status);
create index idx_job_matches_score on public.job_matches(match_score desc);
create index idx_job_matches_created_at on public.job_matches(created_at desc);

-- ─────────────────────────────────────────
-- SOURCE IMPORTS
-- ─────────────────────────────────────────
create table public.source_imports (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references public.users(id) on delete cascade,
  import_type text check (import_type in ('bulk_paste','github_repo')),
  raw_input text,
  urls_found int default 0,
  urls_valid int default 0,
  urls_activated int default 0,
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────
-- SCHEDULER LOGS
-- ─────────────────────────────────────────
create table public.scheduler_logs (
  id uuid default uuid_generate_v4() primary key,
  source_id uuid references public.job_sources(id),
  run_at timestamptz default now(),
  jobs_fetched int default 0,
  jobs_new int default 0,
  jobs_passed int default 0,
  error_message text
);

-- ─────────────────────────────────────────
-- TELEGRAM LINK CODES
-- ─────────────────────────────────────────
create table public.telegram_link_codes (
  id uuid default uuid_generate_v4() primary key,
  telegram_chat_id bigint,
  code text not null,
  expires_at timestamptz not null,
  used boolean default false,
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────
-- ROW LEVEL SECURITY
-- ─────────────────────────────────────────
alter table public.users enable row level security;
alter table public.user_profiles enable row level security;
alter table public.resumes enable row level security;
alter table public.job_sources enable row level security;
alter table public.jobs enable row level security;
alter table public.job_matches enable row level security;
alter table public.source_imports enable row level security;
alter table public.scheduler_logs enable row level security;
alter table public.telegram_link_codes enable row level security;

-- RLS Policies
create policy "users_own" on public.users for all using (auth.uid() = id);
create policy "profiles_own" on public.user_profiles for all using (auth.uid() = user_id);
create policy "resumes_own" on public.resumes for all using (auth.uid() = user_id);
create policy "sources_read_library" on public.job_sources for select using (is_library = true or auth.uid() = user_id);
create policy "sources_manage_own" on public.job_sources for all using (auth.uid() = user_id);
create policy "jobs_read_all" on public.jobs for select using (true);
create policy "matches_own" on public.job_matches for all using (auth.uid() = user_id);
create policy "imports_own" on public.source_imports for all using (auth.uid() = user_id);
create policy "logs_read_all" on public.scheduler_logs for select using (true);
create policy "telegram_codes_all" on public.telegram_link_codes for all using (true);

-- ─────────────────────────────────────────
-- HELPER FUNCTIONS
-- ─────────────────────────────────────────

-- Increment source error count and auto-disable at 3 consecutive errors
create or replace function increment_source_errors(source_id_input uuid)
returns void language plpgsql as $$
begin
  update public.job_sources
  set
    consecutive_errors = consecutive_errors + 1,
    health_status = case
      when consecutive_errors + 1 >= 3 then 'dead'
      else 'degraded'
    end,
    is_active = case
      when consecutive_errors + 1 >= 3 then false
      else is_active
    end
  where id = source_id_input;
end;
$$;
