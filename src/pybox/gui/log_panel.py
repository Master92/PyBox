"""Left sidebar panel – load files, manage log entries, show/hide toggles."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QScrollArea,
    QCheckBox,
    QFrame,
    QSizePolicy,
    QMessageBox,
    QProgressDialog,
    QApplication,
)

from pybox.gui.models import LogEntry, load_log_entry, LOG_COLORS


def _color_icon(hex_color: str, size: int = 14) -> QIcon:
    """Create a small square icon filled with the given color."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setBrush(QBrush(QColor(hex_color)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, 2, 2)
    painter.end()
    return QIcon(pixmap)


class LogItemWidget(QFrame):
    """Single row in the log list – checkbox + color swatch + label."""

    visibility_changed = pyqtSignal(int, bool)   # (entry_index, visible)
    selection_changed = pyqtSignal(int)           # entry_index (clicked for gyro preview)

    def __init__(self, entry: LogEntry, index: int, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.index = index

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            LogItemWidget {
                background: #2d2d2d;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
            LogItemWidget:hover {
                border: 1px solid #666;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(entry.visible)
        self.checkbox.stateChanged.connect(self._on_check_changed)
        layout.addWidget(self.checkbox)

        # Color swatch
        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(
            f"background: {entry.color}; border-radius: 2px; border: none;"
        )
        layout.addWidget(swatch)

        # Label
        label = QLabel(entry.label)
        label.setStyleSheet("color: #ddd; font-size: 12px; border: none;")
        layout.addWidget(label, stretch=1)

        # Duration
        dur_label = QLabel(f"{entry.duration_s:.1f}s")
        dur_label.setStyleSheet("color: #888; font-size: 11px; border: none;")
        layout.addWidget(dur_label)

    def _on_check_changed(self, state):
        visible = state == Qt.CheckState.Checked.value
        self.entry.visible = visible
        self.visibility_changed.emit(self.index, visible)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_changed.emit(self.index)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        if selected:
            self.setStyleSheet("""
                LogItemWidget {
                    background: #3a3a5a;
                    border: 1px solid #7777bb;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                LogItemWidget {
                    background: #2d2d2d;
                    border: 1px solid #444;
                    border-radius: 4px;
                    padding: 4px;
                }
                LogItemWidget:hover {
                    border: 1px solid #666;
                }
            """)


class LogPanel(QWidget):
    """Left sidebar for loading and managing log entries."""

    log_added = pyqtSignal(int)             # index of newly added log
    log_selected = pyqtSignal(int)          # index of log selected for gyro preview
    log_visibility_changed = pyqtSignal()   # any visibility changed
    logs_cleared = pyqtSignal()             # all logs cleared

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list[LogEntry] = []
        self._item_widgets: list[LogItemWidget] = []
        self._selected_index: int = -1
        self._color_counter: int = 0

        self.setMinimumWidth(260)
        self.setMaximumWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel(self.tr("Loaded Logs"))
        title.setStyleSheet("color: #eee; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_load = QPushButton(self.tr("Load File(s)"))
        self.btn_load.setStyleSheet(self._button_style("#4a6fa5"))
        self.btn_load.clicked.connect(self._on_load_files)
        btn_row.addWidget(self.btn_load)

        self.btn_clear = QPushButton(self.tr("Clear All"))
        self.btn_clear.setStyleSheet(self._button_style("#884444"))
        self.btn_clear.clicked.connect(self._on_clear_all)
        btn_row.addWidget(self.btn_clear)

        layout.addLayout(btn_row)

        # Scrollable log list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, stretch=1)

        # Info label at bottom
        self.info_label = QLabel(self.tr("No logs loaded"))
        self.info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.info_label)

    def _button_style(self, bg: str) -> str:
        return f"""
            QPushButton {{
                background: {bg};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {bg}cc;
            }}
            QPushButton:pressed {{
                background: {bg}99;
            }}
        """

    def _on_load_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr("Open Blackbox Log(s)"),
            "",
            self.tr("Blackbox Logs (*.bbl *.bfl *.txt);;All Files (*)"),
        )
        if not files:
            return

        from pybox.decoder.flightlog import FlightLog

        # Count total logs across all files
        total_logs = 0
        file_log_counts = []
        for f in files:
            try:
                fl = FlightLog(f)
                file_log_counts.append((f, fl.log_count))
                total_logs += fl.log_count
            except Exception as e:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to open {path}:\n{error}").format(path=f, error=e))
                file_log_counts.append((f, 0))

        if total_logs == 0:
            return

        progress = QProgressDialog(self.tr("Decoding logs..."), self.tr("Cancel"), 0, total_logs, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)

        loaded = 0
        for file_path, count in file_log_counts:
            for log_idx in range(count):
                if progress.wasCanceled():
                    break
                progress.setValue(loaded)
                progress.setLabelText(f"Decoding {file_path} log {log_idx + 1}/{count}")
                QApplication.processEvents()

                try:
                    entry = load_log_entry(file_path, log_idx, self._color_counter)
                    self._add_entry(entry)
                    self._color_counter += 1
                except Exception as e:
                    QMessageBox.warning(
                        self, self.tr("Decode Error"),
                        self.tr("Failed to decode log {idx} in {path}:\n{error}").format(idx=log_idx + 1, path=file_path, error=e),
                    )
                loaded += 1

        progress.setValue(total_logs)
        self._update_info_label()

    def _add_entry(self, entry: LogEntry):
        idx = len(self.entries)
        self.entries.append(entry)

        item = LogItemWidget(entry, idx)
        item.visibility_changed.connect(self._on_visibility_changed)
        item.selection_changed.connect(self._on_item_selected)
        self._item_widgets.append(item)

        # Insert before the stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, item)

        # Auto-select first entry
        if idx == 0:
            self._on_item_selected(0)

        self.log_added.emit(idx)

    def _on_item_selected(self, index: int):
        if self._selected_index == index:
            return
        # Deselect old
        if 0 <= self._selected_index < len(self._item_widgets):
            self._item_widgets[self._selected_index].set_selected(False)
        self._selected_index = index
        self._item_widgets[index].set_selected(True)
        self.log_selected.emit(index)

    def _on_visibility_changed(self, index: int, visible: bool):
        self.log_visibility_changed.emit()

    def _on_clear_all(self):
        if not self.entries:
            return
        # Remove all widgets
        for w in self._item_widgets:
            self._list_layout.removeWidget(w)
            w.deleteLater()
        self._item_widgets.clear()
        self.entries.clear()
        self._selected_index = -1
        self._color_counter = 0
        self._update_info_label()
        self.logs_cleared.emit()

    def _update_info_label(self):
        n = len(self.entries)
        if n == 0:
            self.info_label.setText(self.tr("No logs loaded"))
        else:
            visible = sum(1 for e in self.entries if e.visible)
            self.info_label.setText(self.tr("{count} log(s) loaded, {visible} visible").format(count=n, visible=visible))

    @property
    def selected_entry(self) -> LogEntry | None:
        if 0 <= self._selected_index < len(self.entries):
            return self.entries[self._selected_index]
        return None
