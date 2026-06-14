-- ForgeSight — LOCAL-DEV ONLY auth shim. Supabase provides the `auth` schema, `auth.users`,
-- and auth.uid(); a plain pgvector container does not. apply_migrations.py applies this first
-- ONLY when auth.users is absent, so migrations.sql FKs + RLS policies resolve locally.
-- NEVER applied on Supabase (auth.users already exists there).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id        uuid,
    aud                text,
    role               text,
    email              text,
    encrypted_password text,
    email_confirmed_at timestamptz,
    created_at         timestamptz,
    updated_at         timestamptz,
    raw_app_meta_data  jsonb,
    raw_user_meta_data jsonb
);

-- auth.uid() returns NULL locally (no JWT context) — RLS policies still parse and the
-- admin-OR clauses simply evaluate to false, which is fine for local graph testing.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
