"""Main application window – assembles all GUI components."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QPushButton,
    QLabel,
    QStatusBar,
    QApplication,
    QMessageBox,
)
from PyQt6.QtGui import QFont, QAction, QActionGroup

from pybox.gui.log_panel import LogPanel
from pybox.gui.gyro_preview import GyroPreviewWidget
from pybox.gui.step_plots import StepResponsePlots
from pybox.gui import i18n
from pybox.gui import theme as theme_mod
from pybox.gui import settings
from pybox.gui.theme import Theme


class MainWindow(QMainWindow):
    """PyBox main window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyBox – Blackbox Log Analyzer")
        self.resize(1400, 900)

        # Restore saved theme
        saved_theme = settings.theme()
        theme_mod.set_theme(saved_theme)
        self._current_theme = theme_mod.current()
        self._apply_theme(self._current_theme)
        self._build_menu_bar()
        self._apply_menu_style(self._current_theme)

        # ── Central widget ────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Left panel: log management ────────────────────────────────
        self.log_panel = LogPanel()
        root_layout.addWidget(self.log_panel)

        # ── Right area: plots ─────────────────────────────────────────
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        root_layout.addWidget(right_splitter, stretch=1)

        # Top: Gyro preview
        gyro_container = QWidget()
        gyro_layout = QVBoxLayout(gyro_container)
        gyro_layout.setContentsMargins(4, 4, 4, 0)
        gyro_layout.setSpacing(2)

        gyro_header = QHBoxLayout()
        self._gyro_title = QLabel(self.tr("Gyro Preview – drag the edges to set analysis range"))
        self._gyro_title.setStyleSheet(f"color: {self._current_theme.fg_dim}; font-size: 11px;")
        gyro_header.addWidget(self._gyro_title)

        self.btn_compute = QPushButton(self.tr("Compute Step Response"))
        self._apply_compute_btn_style(self._current_theme)
        self.btn_compute.setEnabled(False)
        self.btn_compute.clicked.connect(self._on_compute)
        gyro_header.addWidget(self.btn_compute)

        gyro_layout.addLayout(gyro_header)

        self.gyro_preview = GyroPreviewWidget()
        gyro_layout.addWidget(self.gyro_preview)

        right_splitter.addWidget(gyro_container)

        # Bottom: Step response plots + PIDFF table
        self.step_plots = StepResponsePlots()
        right_splitter.addWidget(self.step_plots)

        # Splitter proportions: 30% preview, 70% step response
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 7)

        # ── Status bar ────────────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"color: {self._current_theme.fg_dim}; font-size: 11px;")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(self.tr("Ready – load Blackbox log files to begin"))

        # ── Connect signals ───────────────────────────────────────────
        self.log_panel.log_added.connect(self._on_log_added)
        self.log_panel.log_selected.connect(self._on_log_selected)
        self.log_panel.log_visibility_changed.connect(self._on_visibility_changed)
        self.log_panel.log_removed.connect(self._on_log_removed)
        self.log_panel.logs_cleared.connect(self._on_logs_cleared)
        self.gyro_preview.time_range_changed.connect(self._on_range_changed)

        self._step_computed = False  # True once user has computed step response

        # Restore window geometry
        geom = settings.window_geometry()
        if geom:
            self.restoreGeometry(geom)
        state = settings.window_state()
        if state:
            self.restoreState(state)

    # ── Signal handlers ───────────────────────────────────────────────

    def _on_log_added(self, index: int):
        self.btn_compute.setEnabled(True)
        entry = self.log_panel.entries[index]
        self.status_bar.showMessage(
            self.tr("Loaded: {label} ({dur}s, {rate} Hz)").format(
                label=entry.label, dur=f"{entry.duration_s:.1f}",
                rate=f"{entry.decoded.sample_rate_hz:.0f}")
        )

    def _on_log_selected(self, index: int):
        entry = self.log_panel.entries[index]
        self.gyro_preview.show_entry(entry)
        self.status_bar.showMessage(
            self.tr("Selected: {label} – range: {start}s – {end}s").format(
                label=entry.label,
                start=f"{entry.time_start_s:.1f}",
                end=f"{entry.time_end_s:.1f}")
        )

    def _on_visibility_changed(self):
        # Update step plots if already computed
        entries = self.log_panel.entries
        if any(True for key in self.step_plots._curves):
            self.step_plots.update_plots(entries)
        self.log_panel._update_info_label()

    def _on_log_removed(self):
        """Handle removal of a single log entry."""
        entries = self.log_panel.entries
        if not entries:
            self.gyro_preview.clear_preview()
            self.step_plots.clear_plots()
            self.btn_compute.setEnabled(False)
            self.status_bar.showMessage(self.tr("All logs cleared"))
            return
        # Refresh gyro preview for current selection
        sel = self.log_panel.selected_entry
        self.gyro_preview.show_entry(sel)
        # Refresh step plots if they were computed
        if any(True for key in self.step_plots._curves):
            self.step_plots.update_plots(entries)

    def _on_logs_cleared(self):
        self.gyro_preview.clear_preview()
        self.step_plots.clear_plots()
        self.btn_compute.setEnabled(False)
        self._step_computed = False
        self.status_bar.showMessage(self.tr("All logs cleared"))

    def _on_compute(self):
        entries = self.log_panel.entries
        visible = [e for e in entries if e.visible]
        if not visible:
            self.status_bar.showMessage(self.tr("No visible logs to analyze"))
            return

        self.btn_compute.setEnabled(False)
        self.status_bar.showMessage(self.tr("Computing step responses..."))
        QApplication.processEvents()

        try:
            self.step_plots.update_plots(entries)
            self._step_computed = True
            self.status_bar.showMessage(
                self.tr("Step response computed for {count} log(s)").format(count=len(visible))
            )
        except Exception as e:
            self.status_bar.showMessage(f"Error: {e}")
        finally:
            self.btn_compute.setEnabled(True)

    def _on_range_changed(self, start_s: float, end_s: float):
        """Auto-recompute step response when analysis range changes."""
        if not self._step_computed:
            return
        entries = self.log_panel.entries
        visible = [e for e in entries if e.visible]
        if not visible:
            return
        self.step_plots.update_plots(entries)

    # ── Menu bar ──────────────────────────────────────────────────────

    # Language display names (not translated – always shown in native form)
    _LANG_NAMES = {
        "en": "English",
        "de": "Deutsch",
    }

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet("""
            QMenuBar {
                background: #1e1e1e;
                color: #ccc;
                border-bottom: 1px solid #333;
                font-size: 12px;
            }
            QMenuBar::item:selected { background: #3a3a5a; }
            QMenu {
                background: #2d2d2d;
                color: #ccc;
                border: 1px solid #444;
            }
            QMenu::item:selected { background: #3a3a5a; }
        """)

        # ── Language menu ───────────────────────────────────────────
        self._lang_menu = menu_bar.addMenu(self.tr("Language"))
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)

        current = i18n.current_locale()
        available = ["en"] + i18n.available_locales()

        self._lang_actions: dict[str, QAction] = {}
        for code in available:
            display = self._LANG_NAMES.get(code, code)
            action = QAction(display, self, checkable=True)
            action.setData(code)
            action.setChecked(code == current)
            action.triggered.connect(lambda checked, c=code: self._on_language_changed(c))
            self._lang_group.addAction(action)
            self._lang_menu.addAction(action)
            self._lang_actions[code] = action

        # ── View menu (theme) ──────────────────────────────────────
        self._view_menu = menu_bar.addMenu(self.tr("View"))
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for name in ("dark", "light"):
            label = self.tr("Dark") if name == "dark" else self.tr("Light")
            action = QAction(label, self, checkable=True)
            action.setChecked(name == self._current_theme.name)
            action.triggered.connect(lambda checked, n=name: self._on_theme_changed(n))
            theme_group.addAction(action)
            self._view_menu.addAction(action)
            self._theme_actions[name] = action

        # ── Help menu ──────────────────────────────────────────────
        self._help_menu = menu_bar.addMenu(self.tr("Help"))
        self._about_action = QAction(self.tr("About PyBox"), self)
        self._about_action.triggered.connect(self._on_about)
        self._help_menu.addAction(self._about_action)

    def _on_language_changed(self, locale_code: str):
        """Switch UI language at runtime."""
        if locale_code == i18n.current_locale():
            return
        i18n.install(locale_code)
        settings.set_language(locale_code)
        self._retranslate_ui()

    def _retranslate_ui(self):
        """Refresh all translatable strings in the current window."""
        self.setWindowTitle("PyBox \u2013 Blackbox Log Analyzer")
        self._gyro_title.setText(
            self.tr("Gyro Preview \u2013 drag the edges to set analysis range")
        )
        self.btn_compute.setText(self.tr("Compute Step Response"))
        self.status_bar.showMessage(
            self.tr("Ready \u2013 load Blackbox log files to begin")
        )
        self.log_panel.retranslate_ui()
        # Menus
        self._lang_menu.setTitle(self.tr("Language"))
        self._view_menu.setTitle(self.tr("View"))
        self._theme_actions["dark"].setText(self.tr("Dark"))
        self._theme_actions["light"].setText(self.tr("Light"))
        self._help_menu.setTitle(self.tr("Help"))
        self._about_action.setText(self.tr("About PyBox"))

    def _on_about(self):
        QMessageBox.about(
            self,
            self.tr("About PyBox"),
            self.tr(
                "<h3>PyBox</h3>"
                "<p>Version 0.1.0</p>"
                "<p>Betaflight Blackbox log decoder and analysis tool.</p>"
                "<p>Built with Python, PyQt6, pyqtgraph, NumPy &amp; SciPy.</p>"
                "<p>License: GPLv3</p>"
            ),
        )

    # ── Theming ───────────────────────────────────────────────────────

    def _on_theme_changed(self, name: str):
        t = theme_mod.set_theme(name)
        self._current_theme = t
        settings.set_theme(name)
        self._apply_theme(t)
        # Propagate to children
        self._apply_compute_btn_style(t)
        self._gyro_title.setStyleSheet(f"color: {t.fg_dim}; font-size: 11px;")
        self.status_bar.setStyleSheet(f"color: {t.fg_dim}; font-size: 11px;")
        self.gyro_preview.apply_theme(t)
        self.step_plots.apply_theme(t)
        self.log_panel.apply_theme(t)
        self._apply_menu_style(t)

    def _apply_compute_btn_style(self, t: Theme):
        self.btn_compute.setStyleSheet(f"""
            QPushButton {{
                background: {t.btn_compute_bg};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {t.btn_compute_hover}; }}
            QPushButton:pressed {{ background: {t.btn_compute_pressed}; }}
            QPushButton:disabled {{ background: {t.btn_disabled_bg}; color: {t.btn_disabled_fg}; }}
        """)

    def _apply_menu_style(self, t: Theme):
        self.menuBar().setStyleSheet(f"""
            QMenuBar {{
                background: {t.bg_input};
                color: {t.fg_dim};
                border-bottom: 1px solid {t.border};
                font-size: 12px;
            }}
            QMenuBar::item:selected {{ background: {t.accent_bg}; }}
            QMenu {{
                background: {t.bg_alt};
                color: {t.fg_dim};
                border: 1px solid {t.border};
            }}
            QMenu::item:selected {{ background: {t.accent_bg}; }}
        """)

    def closeEvent(self, event):
        """Save window geometry on close."""
        settings.set_window_geometry(self.saveGeometry())
        settings.set_window_state(self.saveState())
        super().closeEvent(event)

    def _apply_theme(self, t: Theme):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {t.bg};
                color: {t.fg};
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }}
            QSplitter::handle {{
                background: {t.border};
                height: 3px;
            }}
            QSplitter::handle:hover {{
                background: {t.border_light};
            }}
            QStatusBar {{
                background: {t.bg_input};
                border-top: 1px solid {t.border};
            }}
            QScrollBar:vertical {{
                background: {t.bg_alt};
                width: 10px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {t.border_light};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t.fg_dim};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
