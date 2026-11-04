import os
import sys
import shutil
import tempfile
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure QtWebEngineWidgets can be loaded safely in tests without conflict
try:
    from PyQt6.QtCore import Qt, QCoreApplication
    if hasattr(Qt.ApplicationAttribute, "AA_ShareOpenGLContexts"):
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    import PyQt6.QtWebEngineWidgets
except Exception:
    pass

@pytest.fixture(autouse=True, scope="session")
def isolate_test_environment(tmp_path_factory):
    """
    Round 4 Item 2: Test hygiene.
    Redirects all test writes away from the real assets/vault/ and real
    assets/libra_memory.db into an isolated temporary test sandbox.
    Pre-populates existing vault workflows and facts so read-only tests succeed.
    """
    test_sandbox = tmp_path_factory.mktemp("libra_test_sandbox")
    test_vault = test_sandbox / "vault"
    test_vault.mkdir(exist_ok=True)

    # Copy real vault markdown files into test vault so tests have initial state
    real_vault = os.path.join(PROJECT_ROOT, "assets", "vault")
    if os.path.isdir(real_vault):
        for f in os.listdir(real_vault):
            if f.endswith(".md"):
                shutil.copy2(os.path.join(real_vault, f), str(test_vault / f))

    test_db = str(test_sandbox / "test_isolated_memory.db")
    real_db = os.path.join(PROJECT_ROOT, "assets", "libra_memory.db")
    if os.path.isfile(real_db):
        shutil.copy2(real_db, test_db)

    orig_vault = os.environ.get("LIBRA_VAULT_DIR")
    orig_db = os.environ.get("LIBRA_MEMORY_DB")

    os.environ["LIBRA_VAULT_DIR"] = str(test_vault)
    os.environ["LIBRA_MEMORY_DB"] = test_db

    yield

    if orig_vault is not None:
        os.environ["LIBRA_VAULT_DIR"] = orig_vault
    else:
        os.environ.pop("LIBRA_VAULT_DIR", None)

    if orig_db is not None:
        os.environ["LIBRA_MEMORY_DB"] = orig_db
    else:
        os.environ.pop("LIBRA_MEMORY_DB", None)
