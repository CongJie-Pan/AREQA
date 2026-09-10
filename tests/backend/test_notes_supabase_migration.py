"""Tests for the Supabase notes persistence migration."""

from pathlib import Path


MIGRATION = Path("supabase/migrations/20260909000000_user_notes.sql")
ORGANIZATION_MIGRATION = Path("supabase/migrations/20260910000000_notes_organization_metadata.sql")


def test_notes_migration_creates_owner_scoped_synced_notes_table() -> None:
    """Verify the notes migration includes persistence, RLS, and source links."""
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "create table if not exists public.notes" in sql
    assert "content_snapshot text not null" in sql
    assert "answer_blocks_snapshot jsonb" in sql
    assert "constraint notes_user_message_unique unique (user_id, message_id)" in sql
    assert "foreign key (conversation_id) references public.conversations(id)" in sql
    assert "foreign key (message_id) references public.messages(id)" in sql
    assert "alter table public.notes enable row level security" in sql
    assert "create policy notes_owner_select" in sql
    assert "create policy notes_owner_insert" in sql
    assert "create policy notes_owner_delete" in sql
    assert "m.role = 'assistant'" in sql


def test_notes_organization_migration_adds_synced_metadata() -> None:
    """Verify notes can sync pinned state and manual tags."""
    sql = ORGANIZATION_MIGRATION.read_text(encoding="utf-8")

    assert "add column if not exists tags text[] not null default '{}'" in sql
    assert "add column if not exists is_pinned boolean not null default false" in sql
    assert "idx_notes_user_pinned_created_at" in sql
    assert "idx_notes_user_tags" in sql
