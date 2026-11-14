-- Provenance is a snapshot and intentionally survives deletion of the source conversation.
alter table public.conversations add column if not exists branch_origin jsonb;
alter table public.messages add column if not exists attachment_source_id uuid;
