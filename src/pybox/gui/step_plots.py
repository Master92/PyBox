"""Step response plots (Roll/Pitch/Yaw) with PIDFF config table."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
)
from PyQt6.QtGui import QColor

from pybox.gui.models import LogEntry
from pybox.analysis.step_response import estimate_step_response
from pybox.gui.theme import Theme, current as current_theme


AXIS_NAMES = ["Roll", "Pitch", "Yaw"]


class StepResponsePlots(QWidget):
    """Three step response plots (Roll, Pitch, Yaw) + PIDFF config table.

    All visible logs are overlaid in each plot with their assigned colors.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splitter: plots on top, table on bottom
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # ── Plots area ────────────────────────────────────────────────
        plots_widget = pg.GraphicsLayoutWidget()
        plots_widget.setBackground("#1e1e1e")
        splitter.addWidget(plots_widget)

        self._graphics = plots_widget
        self._plots: list[pg.PlotItem] = []
        self._ref_lines: list[pg.InfiniteLine] = []
        self._curves: dict[tuple[int, int], pg.PlotDataItem] = {}  # (log_idx, axis) → curve

        for i, name in enumerate(AXIS_NAMES):
            if i > 0:
                plots_widget.nextRow()
            plot = plots_widget.addPlot(row=i, col=0)
            plot.setTitle(name, color="#ddd", size="12pt")
            plot.setLabel("bottom", "Time (ms)")
            plot.setLabel("left", "Response")
            plot.showGrid(x=True, y=True, alpha=0.15)
            plot.getAxis("bottom").setPen("#888")
            plot.getAxis("left").setPen("#888")
            plot.setYRange(0, 1.5)
            plot.setXRange(0, 500, padding=0)
            plot.setLimits(xMin=0, xMax=500)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()

            # Reference line at y=1 (steady state)
            ref_line = pg.InfiniteLine(
                pos=1.0,
                angle=0,
                pen=pg.mkPen("#555555", width=1, style=Qt.PenStyle.DashLine),
            )
            plot.addItem(ref_line)

            self._plots.append(plot)
            self._ref_lines.append(ref_line)

        # Link X axes
        for i in range(1, 3):
            self._plots[i].setXLink(self._plots[0])

        # ── PIDFF Config Table ────────────────────────────────────────
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(8, 4, 8, 4)

        self._table_title = QLabel(self.tr("PIDFF Configuration"))
        self._table_title.setStyleSheet("color: #ccc; font-size: 13px; font-weight: bold;")
        table_layout.addWidget(self._table_title)

        self._table = QTableWidget()
        self._table.setStyleSheet("""
            QTableWidget {
                background: #1e1e1e;
                color: #ddd;
                gridline-color: #444;
                border: 1px solid #444;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 2px 6px;
            }
            QHeaderView::section {
                background: #2d2d2d;
                color: #ccc;
                border: 1px solid #444;
                padding: 3px 6px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Log", "Color", "Roll PIDFF", "Pitch PIDFF", "Yaw PIDFF", "File", "Duration",
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 40)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setMaximumHeight(180)

        table_layout.addWidget(self._table)
        splitter.addWidget(table_container)

        # Splitter proportions: 75% plots, 25% table
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    def update_plots(self, entries: list[LogEntry]):
        """Recompute and redraw step responses for all visible entries."""
        # Remove old curves
        for (log_idx, axis), curve in self._curves.items():
            self._plots[axis].removeItem(curve)
        self._curves.clear()

        # Clear legends
        for plot in self._plots:
            if plot.legend is not None:
                plot.legend.clear()

        for log_idx, entry in enumerate(entries):
            if not entry.visible:
                continue
            self._compute_and_plot(entry, log_idx)

        # Keep fixed Y range for consistent comparison
        for plot in self._plots:
            plot.setYRange(0, 1.5)

        # Update table
        self._update_table(entries)

    def _compute_and_plot(self, entry: LogEntry, log_idx: int):
        """Compute step response for one log and add traces to all 3 plots."""
        time_s, gyro_r, gyro_p, gyro_y = entry.gyro_arrays()
        sp_r, sp_p, sp_y = entry.setpoint_arrays()

        if len(time_s) == 0:
            return

        mask = entry.time_mask()
        gyros = [gyro_r[mask], gyro_p[mask], gyro_y[mask]]
        setpoints = [sp_r[mask], sp_p[mask], sp_y[mask]]

        # Estimate sample rate from time array
        dt = np.median(np.diff(time_s[mask])) if np.sum(mask) > 2 else 0.001
        sr_khz = 1.0 / (dt * 1000.0) if dt > 0 else 4.0

        color = entry.color
        pen = pg.mkPen(color, width=2)

        for axis in range(3):
            if len(setpoints[axis]) < 100:
                continue

            result = estimate_step_response(
                setpoints[axis],
                gyros[axis],
                sr_khz,
            )

            if len(result.mean_response) == 0:
                continue

            curve = self._plots[axis].plot(
                result.time_ms,
                result.mean_response,
                pen=pen,
                name=entry.label,
            )
            self._curves[(log_idx, axis)] = curve

    def _update_table(self, entries: list[LogEntry]):
        """Refresh the PIDFF config table."""
        self._table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            # Label
            label_item = QTableWidgetItem(entry.label)
            if not entry.visible:
                label_item.setForeground(QColor("#666"))
            self._table.setItem(row, 0, label_item)

            # Color swatch
            color_item = QTableWidgetItem("  ")
            color_item.setBackground(QColor(entry.color))
            self._table.setItem(row, 1, color_item)

            # PIDFF per axis
            pidff = entry.pidff
            self._table.setItem(row, 2, QTableWidgetItem(pidff.axis_str(0)))
            self._table.setItem(row, 3, QTableWidgetItem(pidff.axis_str(1)))
            self._table.setItem(row, 4, QTableWidgetItem(pidff.axis_str(2)))

            # File
            from pathlib import Path
            self._table.setItem(row, 5, QTableWidgetItem(Path(entry.file_path).name))

            # Duration (selected range)
            range_s = entry.time_end_s - entry.time_start_s
            self._table.setItem(row, 6, QTableWidgetItem(f"{range_s:.1f}s"))

    def clear_plots(self):
        """Remove all curves and clear the table."""
        for (log_idx, axis), curve in self._curves.items():
            self._plots[axis].removeItem(curve)
        self._curves.clear()
        for plot in self._plots:
            if plot.legend is not None:
                plot.legend.clear()
        self._table.setRowCount(0)

    def set_log_visibility(self, entries: list[LogEntry], log_idx: int, visible: bool):
        """Show/hide a specific log's traces."""
        for axis in range(3):
            key = (log_idx, axis)
            if key in self._curves:
                self._curves[key].setVisible(visible)
        self._update_table(entries)

    def apply_theme(self, t: Theme):
        """Update colors to match the given theme."""
        self._graphics.setBackground(t.plot_bg)
        for i, plot in enumerate(self._plots):
            plot.setTitle(AXIS_NAMES[i], color=t.plot_title_color, size="12pt")
            plot.getAxis("bottom").setPen(t.plot_axis)
            plot.getAxis("left").setPen(t.plot_axis)
            plot.showGrid(x=True, y=True, alpha=t.plot_grid_alpha)
        for ref in self._ref_lines:
            ref.setPen(pg.mkPen(t.plot_ref_line, width=1, style=Qt.PenStyle.DashLine))
        self._table_title.setStyleSheet(
            f"color: {t.fg_dim}; font-size: 13px; font-weight: bold;"
        )
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {t.bg_input};
                color: {t.fg};
                gridline-color: {t.border};
                border: 1px solid {t.border};
                font-size: 11px;
            }}
            QTableWidget::item {{
                padding: 2px 6px;
            }}
            QHeaderView::section {{
                background: {t.bg_alt};
                color: {t.fg_dim};
                border: 1px solid {t.border};
                padding: 3px 6px;
                font-weight: bold;
                font-size: 11px;
            }}
        """)

