import os
import sys
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QComboBox, QTextEdit, QMessageBox
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory import SemanticMemory, MemoryCore


class FactCard(QFrame):
    pin_toggled = pyqtSignal(int, bool)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(int)

    def __init__(self, fact: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.fact = fact
        self.fact_id = fact["id"]
        self.pinned = fact.get("pinned", False)
        self.init_ui()

    def init_ui(self):
        self.setObjectName("FactCard")
        border_color = "#f59e0b" if self.pinned else "#1e293b"
        bg_color = "#091220" if self.pinned else "#050b14"

        self.setStyleSheet(f"""
            QFrame#FactCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 10px;
            }}
            QFrame#FactCard:hover {{
                border-color: #00ffcc;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header: Pin | Entity.Relation | Category | Timestamp
        header = QHBoxLayout()
        header.setSpacing(8)

        self.pin_btn = QPushButton("★" if self.pinned else "☆")
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.setFont(QFont("Segoe UI Symbol", 12))
        pin_color = "#f59e0b" if self.pinned else "#64748b"
        self.pin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {pin_color};
                border: none; font-size: 14px;
            }}
            QPushButton:hover {{ color: #fbbf24; }}
        """)
        self.pin_btn.setToolTip("Pin fact (protects from Markovian eviction)")
        self.pin_btn.clicked.connect(self._toggle_pin)
        header.addWidget(self.pin_btn)

        key_label = QLabel(f"{self.fact.get('entity', '')}.{self.fact.get('relation', '')}")
        key_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        key_label.setStyleSheet("color: #00ffcc;")
        header.addWidget(key_label)

        header.addStretch()

        cat_badge = QLabel(f"[{self.fact.get('category', 'general').upper()}]")
        cat_badge.setFont(QFont("Segoe UI", 8))
        cat_badge.setStyleSheet("color: #38bdf8; background: #0c1c2e; padding: 2px 6px; border-radius: 4px;")
        header.addWidget(cat_badge)

        time_str = str(self.fact.get("updated_at", ""))[:16]
        time_lbl = QLabel(time_str)
        time_lbl.setFont(QFont("Segoe UI", 7))
        time_lbl.setStyleSheet("color: #64748b;")
        header.addWidget(time_lbl)

        layout.addLayout(header)

        # Fact value body
        self.body_label = QLabel(self.fact.get("value", ""))
        self.body_label.setFont(QFont("Segoe UI", 9))
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet("color: #e2e8f0; line-height: 1.4;")
        layout.addWidget(self.body_label)

        # Action Buttons: Edit, Delete
        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addStretch()

        edit_btn = QPushButton("EDIT")
        edit_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #0c1829; color: #38bdf8;
                border: 1px solid #142a47; border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover { background-color: #12253f; border-color: #38bdf8; }
        """)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.fact))
        actions.addWidget(edit_btn)

        del_btn = QPushButton("DELETE")
        del_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a0f14; color: #f43f5e;
                border: 1px solid #381520; border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover { background-color: #2e1018; border-color: #f43f5e; }
        """)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.fact_id))
        actions.addWidget(del_btn)

        layout.addLayout(actions)

    def _toggle_pin(self):
        new_state = not self.pinned
        self.pin_toggled.emit(self.fact_id, new_state)


class EditFactDialog(QDialog):
    def __init__(self, fact: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.fact = fact
        self.setWindowTitle("EDIT MEMORY FACT // OBSIDIAN VAULT")
        self.resize(520, 280)
        self.setStyleSheet("background-color: #060b14; color: #f1f5f9;")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel(f"EDIT FACT: {self.fact.get('entity', '')}.{self.fact.get('relation', '')}")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #00ffcc;")
        layout.addWidget(title)

        # Category
        cat_layout = QHBoxLayout()
        cat_lbl = QLabel("Category:")
        cat_lbl.setFont(QFont("Segoe UI", 9))
        self.cat_edit = QLineEdit(self.fact.get("category", "general"))
        self.cat_edit.setFont(QFont("Segoe UI", 9))
        self.cat_edit.setStyleSheet("background-color: #0a1424; color: #38bdf8; border: 1px solid rgba(255, 255, 255, 0.08); padding: 4px;")
        cat_layout.addWidget(cat_lbl)
        cat_layout.addWidget(self.cat_edit)
        layout.addLayout(cat_layout)

        # Body text
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(self.fact.get("value", ""))
        self.text_edit.setFont(QFont("Segoe UI", 10))
        self.text_edit.setStyleSheet("background-color: #04070e; color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.08); padding: 8px;")
        layout.addWidget(self.text_edit)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFont(QFont("Segoe UI", 9))
        cancel_btn.setStyleSheet("background: #0d1522; color: #94a3b8; border: 1px solid #1e293b; padding: 6px 14px;")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        save_btn = QPushButton("SAVE NOTE")
        save_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        save_btn.setStyleSheet("background: #fafafa; color: #09090b; border: 1px solid #fafafa; padding: 6px 14px;")
        save_btn.clicked.connect(self.accept)
        btns.addWidget(save_btn)

        layout.addLayout(btns)

    def get_data(self) -> Dict[str, str]:
        return {
            "value": self.text_edit.toPlainText().strip(),
            "category": self.cat_edit.text().strip()
        }


class MemoryVaultWidget(QDialog):
    """
    Inspectable Memory Vault Window (v11.0 / Phase 11).
    Displays human-readable Markdown-synced semantic memory facts with instant
    FTS5 BM25 search, category filters, and one-click edit/pin/delete.
    """

    def __init__(self, memory: Optional[SemanticMemory] = None, parent=None):
        super().__init__(parent)
        self.memory = memory or SemanticMemory()
        self.setWindowTitle("LIBRA AI // MEMORY VAULT (OBSIDIAN SYNC)")
        self.resize(920, 680)
        self.setStyleSheet("background-color: #09090b; color: #f8fafc; font-family: 'Segoe UI', sans-serif;")
        self.init_ui()
        self.refresh_facts()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # 1. Header Row
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("◈ Memory Vault")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; letter-spacing: -0.2px;")
        sub = QLabel(f"BI-DIRECTIONAL OBSIDIAN SYNC: assets/vault/ (*.md)")
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet("color: #64748b;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        header.addLayout(title_box)

        header.addStretch()

        self.vault_path_btn = QPushButton("📂 OPEN VAULT FOLDER")
        self.vault_path_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.vault_path_btn.setStyleSheet("""
            QPushButton {
                background: #18181b; color: #f4f4f5;
                border: 1px solid #142a47; border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { border-color: #00ffcc; }
        """)
        self.vault_path_btn.clicked.connect(self._open_vault_folder)
        header.addWidget(self.vault_path_btn)

        main_layout.addLayout(header)

        # 2. Controls: Instant Search (FTS5) + Category Filter + Add Fact Button
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Instant search memory notes (FTS5 BM25)...")
        self.search_box.setFont(QFont("Segoe UI", 10))
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #18181b; color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 8px 12px;
            }
            QLineEdit:focus { border-color: #00ffcc; }
        """)
        self.search_box.textChanged.connect(self.refresh_facts)
        controls.addWidget(self.search_box, stretch=6)

        self.cat_filter = QComboBox()
        self.cat_filter.setFont(QFont("Segoe UI", 9))
        self.cat_filter.setStyleSheet("""
            QComboBox {
                background-color: #060c18; color: #38bdf8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 7px 10px;
            }
        """)
        self.cat_filter.addItem("ALL CATEGORIES")
        self.cat_filter.currentTextChanged.connect(self.refresh_facts)
        controls.addWidget(self.cat_filter, stretch=3)

        add_btn = QPushButton("+ NEW FACT")
        add_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        add_btn.setStyleSheet("""
            QPushButton {
                background: #fafafa; color: #09090b;
                border: 1px solid #fafafa; border-radius: 6px; padding: 8px 14px;
            }
            QPushButton:hover { background: #059669; }
        """)
        add_btn.clicked.connect(self._create_fact_dialog)
        controls.addWidget(add_btn, stretch=2)

        main_layout.addLayout(controls)

        # 3. Facts Card Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.scroll_content = QWidget()
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(10)
        self.scroll.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll)

    def refresh_facts(self):
        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        query = self.search_box.text().strip()
        cat_text = self.cat_filter.currentText()
        category = None if cat_text in ["", "ALL CATEGORIES"] else cat_text

        facts = self.memory.get_vault_facts(query=query if query else None, category=category)

        # Update categories list in combobox
        all_categories = sorted(list(set(f.get("category", "general") for f in self.memory.get_vault_facts())))
        current_cat = self.cat_filter.currentText()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItem("ALL CATEGORIES")
        for c in all_categories:
            if c:
                self.cat_filter.addItem(c.upper())
        idx = self.cat_filter.findText(current_cat)
        if idx >= 0:
            self.cat_filter.setCurrentIndex(idx)
        self.cat_filter.blockSignals(False)

        if not facts:
            no_data = QLabel("No memory vault notes found matching query.")
            no_data.setFont(QFont("Segoe UI", 10))
            no_data.setStyleSheet("color: #64748b; padding: 20px;")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.addWidget(no_data)
        else:
            for fact in facts:
                card = FactCard(fact, self.scroll_content)
                card.pin_toggled.connect(self._on_pin_toggled)
                card.edit_requested.connect(self._on_edit_fact)
                card.delete_requested.connect(self._on_delete_fact)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def _on_pin_toggled(self, fact_id: int, new_pinned: bool):
        self.memory.pin_vault_fact(fact_id, new_pinned)
        self.refresh_facts()

    def _on_edit_fact(self, fact: Dict[str, Any]):
        dlg = EditFactDialog(fact, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data["value"]:
                self.memory.update_vault_fact(fact["id"], data["value"], category=data["category"])
                self.refresh_facts()

    def _on_delete_fact(self, fact_id: int):
        reply = QMessageBox.question(
            self,
            "DELETE MEMORY FACT",
            f"Are you sure you want to permanently delete this fact note from memory and assets/vault/?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.memory.delete_vault_fact(fact_id)
            self.refresh_facts()

    def _create_fact_dialog(self):
        new_fact = {"id": 0, "entity": "user", "relation": "note", "value": "", "category": "general", "pinned": False}
        dlg = EditFactDialog(new_fact, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data["value"]:
                self.memory.upsert_semantic_fact(
                    entity="user",
                    relation=f"fact_{int(time.time())}",
                    value=data["value"],
                    category=data["category"],
                    pinned=False
                )
                self.refresh_facts()

    def _open_vault_folder(self):
        if sys.platform == "win32" and self.memory.vault_dir and os.path.isdir(self.memory.vault_dir):
            import subprocess
            subprocess.Popen(["explorer.exe", os.path.normpath(self.memory.vault_dir)])
