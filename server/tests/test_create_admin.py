"""scripts/create_admin.py's file handling: it must update settings in place and never
duplicate an admin id (the Supabase call itself needs a real project)."""

from __future__ import annotations

from scripts.create_admin import merge_ids, upsert_env


def test_upsert_replaces_a_setting_and_keeps_the_rest(tmp_path):
    env = tmp_path / ".env"
    env.write_text("AUTH_MODE=dev\nADMIN_USER_IDS=old\nSUPABASE_URL=https://x\n", encoding="utf-8")
    upsert_env(env, "ADMIN_USER_IDS", "old,new")
    upsert_env(env, "VITE_SUPABASE_URL", "https://x")
    assert env.read_text(encoding="utf-8").splitlines() == [
        "AUTH_MODE=dev", "ADMIN_USER_IDS=old,new", "SUPABASE_URL=https://x", "VITE_SUPABASE_URL=https://x"]


def test_admin_ids_are_merged_without_duplicates():
    assert merge_ids("", "a") == "a"
    assert merge_ids("a, b", "b") == "a,b"
    assert merge_ids("a", "c") == "a,c"
