import os
import sys

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
