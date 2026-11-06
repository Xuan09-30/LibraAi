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

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow audio/large-model benchmarks")

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

    test_soul = str(test_sandbox / "SOUL.md")
    real_soul = os.path.join(PROJECT_ROOT, "assets", "SOUL.md")
    if os.path.isfile(real_soul):
        shutil.copy2(real_soul, test_soul)

    test_user = str(test_sandbox / "USER.md")
    real_user = os.path.join(PROJECT_ROOT, "assets", "USER.md")
    if os.path.isfile(real_user):
        shutil.copy2(real_user, test_user)

    test_lessons = str(test_sandbox / "LESSONS.md")
    real_lessons = os.path.join(PROJECT_ROOT, "assets", "LESSONS.md")
    if os.path.isfile(real_lessons):
        shutil.copy2(real_lessons, test_lessons)

    test_skills = str(test_sandbox / "skills")
    real_skills = os.path.join(PROJECT_ROOT, "skills")
    if os.path.isdir(real_skills):
        shutil.copytree(real_skills, test_skills, dirs_exist_ok=True)

    test_plots = str(test_sandbox / "plots")
    os.makedirs(test_plots, exist_ok=True)

    test_uploads = str(test_sandbox / "uploads")
    os.makedirs(test_uploads, exist_ok=True)

    test_assets = str(test_sandbox / "assets")
    os.makedirs(test_assets, exist_ok=True)

    orig_vault = os.environ.get("LIBRA_VAULT_DIR")
    orig_db = os.environ.get("LIBRA_MEMORY_DB")
    orig_soul = os.environ.get("LIBRA_SOUL_PATH")
    orig_user = os.environ.get("LIBRA_USER_PATH")
    orig_lessons = os.environ.get("LIBRA_LESSONS_PATH")
    orig_skills = os.environ.get("LIBRA_SKILLS_DIR")
    orig_plots = os.environ.get("LIBRA_PLOTS_DIR")
    orig_uploads = os.environ.get("LIBRA_UPLOADS_DIR")
    orig_assets = os.environ.get("LIBRA_ASSETS_DIR")

    os.environ["LIBRA_VAULT_DIR"] = str(test_vault)
    os.environ["LIBRA_MEMORY_DB"] = test_db
    os.environ["LIBRA_SOUL_PATH"] = test_soul
    os.environ["LIBRA_USER_PATH"] = test_user
    os.environ["LIBRA_LESSONS_PATH"] = test_lessons
    os.environ["LIBRA_SKILLS_DIR"] = test_skills
    os.environ["LIBRA_PLOTS_DIR"] = test_plots
    os.environ["LIBRA_UPLOADS_DIR"] = test_uploads
    os.environ["LIBRA_ASSETS_DIR"] = test_assets

    yield

    for k, v in [
        ("LIBRA_VAULT_DIR", orig_vault),
        ("LIBRA_MEMORY_DB", orig_db),
        ("LIBRA_SOUL_PATH", orig_soul),
        ("LIBRA_USER_PATH", orig_user),
        ("LIBRA_LESSONS_PATH", orig_lessons),
        ("LIBRA_SKILLS_DIR", orig_skills),
        ("LIBRA_PLOTS_DIR", orig_plots),
        ("LIBRA_UPLOADS_DIR", orig_uploads),
        ("LIBRA_ASSETS_DIR", orig_assets),
    ]:
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
