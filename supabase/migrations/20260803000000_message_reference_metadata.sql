-- Persist assistant response metadata required to reconstruct citations and
-- source detail panels across devices.
alter table public.messages
  add column if not exists citations jsonb,
  add column if not exists search_results jsonb,
  add column if not exists sources jsonb,
  add column if not exists suggestions jsonb,
  add column if not exists reasoning jsonb;

alter table public.messages
  drop constraint if exists messages_citations_is_array,
  drop constraint if exists messages_search_results_is_array,
  drop constraint if exists messages_sources_is_array,
  drop constraint if exists messages_suggestions_is_array,
  drop constraint if exists messages_reasoning_is_object;

alter table public.messages
  add constraint messages_citations_is_array
  check (citations is null or jsonb_typeof(citations) = 'array'),
  add constraint messages_search_results_is_array
  check (search_results is null or jsonb_typeof(search_results) = 'array'),
  add constraint messages_sources_is_array
  check (sources is null or jsonb_typeof(sources) = 'array'),
  add constraint messages_suggestions_is_array
  check (suggestions is null or jsonb_typeof(suggestions) = 'array'),
  add constraint messages_reasoning_is_object
  check (reasoning is null or jsonb_typeof(reasoning) = 'object');
