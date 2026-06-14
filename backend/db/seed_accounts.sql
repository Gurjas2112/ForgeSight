-- ForgeSight — seeded, pre-confirmed demo accounts (forgesight-v3-final.md §Tier 1).
-- Engineer = primary login; Admin = judging login (adds SIMULATE + Admin Console).
-- Password for both: 'forgesight-demo'. Email verification OFF for seeds (prototype posture).
--
-- NOTE: Supabase manages auth.users. Direct inserts work for a self-hosted/seed scenario;
-- on hosted Supabase prefer the Admin API (auth.admin.createUser) — apply_migrations.py uses
-- the service-role key + GoTrue admin endpoint when available and falls back to this SQL.

-- Engineer ------------------------------------------------------------------------------
INSERT INTO auth.users
  (instance_id, id, aud, role, email, encrypted_password,
   email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data)
VALUES
  ('00000000-0000-0000-0000-000000000000',
   '11111111-1111-1111-1111-111111111111', 'authenticated', 'authenticated',
   'engineer@demo.forgesight', crypt('forgesight-demo', gen_salt('bf')),
   now(), now(), now(),
   '{"provider":"email","providers":["email"],"role":"engineer"}'::jsonb,
   '{"full_name":"Arjun (Engineer)"}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- Admin ---------------------------------------------------------------------------------
INSERT INTO auth.users
  (instance_id, id, aud, role, email, encrypted_password,
   email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data)
VALUES
  ('00000000-0000-0000-0000-000000000000',
   '22222222-2222-2222-2222-222222222222', 'authenticated', 'authenticated',
   'admin@demo.forgesight', crypt('forgesight-demo', gen_salt('bf')),
   now(), now(), now(),
   '{"provider":"email","providers":["email"],"role":"admin"}'::jsonb,
   '{"full_name":"Plant Admin"}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- Mirror into profiles (role drives RLS + agent role-overlay) ----------------------------
INSERT INTO profiles (id, full_name, role, area) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Arjun (Engineer)', 'engineer', 'Rolling'),
  ('22222222-2222-2222-2222-222222222222', 'Plant Admin',      'admin',    'Plant')
ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name;
