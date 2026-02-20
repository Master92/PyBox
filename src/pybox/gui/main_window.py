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
)
from PyQt6.QtGui import QFont

from pybox.gui.log_panel import LogPanel
from pybox.gui.gyro_preview import GyroPreviewWidget
from pybox.gui.step_plots import StepResponsePlots


class MainWindow(QMainWindow):
    """PyBox main window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyBox – Blackbox Log Analyzer")
        self.resize(1400, 900)

        self._apply_dark_theme()

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
        gyro_title = QLabel("Gyro Preview – drag the shaded region to set analysis range")
        gyro_title.setStyleSheet("color: #aaa; font-size: 11px;")
        gyro_header.addWidget(gyro_title)

        self.btn_compute = QPushButton("Compute Step Response")
        self.btn_compute.setStyleSheet("""
            QPushButton {
                background: #4a8a4a;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #5a9a5a; }
            QPushButton:pressed { background: #3a7a3a; }
            QPushButton:disabled { background: #444; color: #888; }
        """)
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
        self.status_bar.setStyleSheet("color: #aaa; font-size: 11px;")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready – load Blackbox log files to begin")

        # ── Connect signals ───────────────────────────────────────────
        self.log_panel.log_added.connect(self._on_log_added)
        self.log_panel.log_selected.connect(self._on_log_selected)
        self.log_panel.log_visibility_changed.connect(self._on_visibility_changed)
        self.log_panel.logs_cleared.connect(self._on_logs_cleared)

    # ── Signal handlers ───────────────────────────────────────────────

    def _on_log_added(self, index: int):
        self.btn_compute.setEnabled(True)
        entry = self.log_panel.entries[index]
        self.status_bar.showMessage(
            f"Loaded: {entry.label} ({entry.duration_s:.1f}s, "
            f"{entry.decoded.sample_rate_hz:.0f} Hz)"
        )

    def _on_log_selected(self, index: int):
        entry = self.log_panel.entries[index]
        self.gyro_preview.show_entry(entry)
        self.status_bar.showMessage(
            f"Selected: {entry.label} – range: "
            f"{entry.time_start_s:.1f}s – {entry.time_end_s:.1f}s"
        )

    def _on_visibility_changed(self):
        # Update step plots if already computed
        entries = self.log_panel.entries
        if any(True for key in self.step_plots._curves):
            self.step_plots.update_plots(entries)
        self.log_panel._update_info_label()

    def _on_logs_cleared(self):
        self.gyro_preview.clear_preview()
        self.step_plots.clear_plots()
        self.btn_compute.setEnabled(False)
        self.status_bar.showMessage("All logs cleared")

    def _on_compute(self):
        entries = self.log_panel.entries
        visible = [e for e in entries if e.visible]
        if not visible:
            self.status_bar.showMessage("No visible logs to analyze")
            return

        self.btn_compute.setEnabled(False)
        self.status_bar.showMessage("Computing step responses...")
        QApplication.processEvents()

        try:
            self.step_plots.update_plots(entries)
            self.status_bar.showMessage(
                f"Step response computed for {len(visible)} log(s)"
            )
        except Exception as e:
            self.status_bar.showMessage(f"Error: {e}")
        finally:
            self.btn_compute.setEnabled(True)

    # ── Theming ───────────────────────────────────────────────────────

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #252525;
                color: #ddd;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }
            QSplitter::handle {
                background: #333;
                height: 3px;
            }
            QSplitter::handle:hover {
                background: #555;
            }
            QStatusBar {
                background: #1e1e1e;
                border-top: 1px solid #333;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #777;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
