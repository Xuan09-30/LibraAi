import os
import time
import pytest
from tools.computer_use_agent import AutonomousComputerUseAgent
from core.memory import SemanticMemory

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def test_computer_use_never_writes_real_vault_in_tests():
    real_vault_file = os.path.join(PROJECT_ROOT, "assets", "vault", "learned_workflow_cinejoy_pk.md")
    assert os.path.exists(real_vault_file)
    with open(real_vault_file, "r", encoding="utf-8") as f:
        orig_content = f.read()
    orig_mtime = os.path.getmtime(real_vault_file)

    agent = AutonomousComputerUseAgent(gui_control=None, spatial=None)
    res = agent.execute_task(
        "Open my chrome and then cinejoy.pk, find and search hannibal and click resume",
        dry_run=True,
        post_condition={"expected_screen_text": "hannibal", "simulated_state": {"screen_text": "Hannibal - Now Playing"}}
    )
    assert res["status"] == "success"

    # Verify real vault file was NOT modified
    with open(real_vault_file, "r", encoding="utf-8") as f:
        new_content = f.read()
    new_mtime = os.path.getmtime(real_vault_file)

    assert new_mtime == orig_mtime, "Test modified real assets/vault/learned_workflow_cinejoy_pk.md mtime!"
    assert new_content == orig_content, "Test modified real assets/vault/learned_workflow_cinejoy_pk.md content!"

    # Verify the workflow was written to the isolated test vault
    test_vault_dir = os.environ.get("LIBRA_VAULT_DIR")
    assert test_vault_dir is not None
    assert test_vault_dir != os.path.join(PROJECT_ROOT, "assets", "vault")
    isolated_vault_file = os.path.join(test_vault_dir, "learned_workflow_cinejoy_pk.md")
    assert os.path.exists(isolated_vault_file)


def test_semantic_memory_never_writes_real_db_or_vault():
    real_db_path = os.path.join(PROJECT_ROOT, "assets", "libra_memory.db")
    real_vault_dir = os.path.join(PROJECT_ROOT, "assets", "vault")
    orig_db_mtime = os.path.getmtime(real_db_path) if os.path.exists(real_db_path) else 0
    orig_vault_files = set(os.listdir(real_vault_dir))

    mem = SemanticMemory()
    assert mem.db_path != real_db_path, f"SemanticMemory must not point to real DB path: {mem.db_path}"
    assert mem.vault_dir != real_vault_dir, f"SemanticMemory must not point to real vault dir: {mem.vault_dir}"

    fact_id = mem.upsert_semantic_fact("hygiene_test_user", "test_hygiene_key", "test_hygiene_val", user_email="host@libra.local")
    assert fact_id > 0

    if os.path.exists(real_db_path):
        assert os.path.getmtime(real_db_path) == orig_db_mtime, "Real assets/libra_memory.db was modified during test!"
    new_vault_files = set(os.listdir(real_vault_dir))
    assert new_vault_files == orig_vault_files, f"Real assets/vault received new files: {new_vault_files - orig_vault_files}"
