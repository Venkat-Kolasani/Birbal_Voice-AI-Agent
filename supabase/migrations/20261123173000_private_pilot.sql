begin;

create table public.pilot_interviews (
    owner_id uuid not null references auth.users(id) on delete cascade,
    id text not null check (id ~ '^[0-9a-f]{32}$'),
    updated_at timestamptz not null default now(),
    data jsonb not null check (jsonb_typeof(data) = 'object'),
    primary key (owner_id, id)
);

create index pilot_interviews_recent on public.pilot_interviews (owner_id, updated_at desc, id);
alter table public.pilot_interviews enable row level security;
revoke all on public.pilot_interviews from public, anon, authenticated;
grant select, insert, update on public.pilot_interviews to service_role;

commit;
