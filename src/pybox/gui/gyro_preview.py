"""Gyro preview plot with draggable start/end time region for epoch selection."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
import numpy as np
import pyqtgraph as pg

from pybox.gui.models import LogEntry
from pybox.gui.theme import Theme, current as current_theme


class GyroPreviewWidget(QWidget):
    """Shows gyro traces for the currently selected log with a draggable
    LinearRegionItem to set the analysis time range.

    The legend is rendered as a fixed label row below the plot."""

    time_range_changed = pyqtSignal(float, float)  # (start_s, end_s)

    AXIS_COLORS = ["#ff6666", "#66ff66", "#6688ff"]  # Roll, Pitch, Yaw
    AXIS_NAMES = ["Roll", "Pitch", "Yaw"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)

        self._entry: LogEntry | None = None
        self._curves: list[pg.PlotDataItem] = []
        self._region: pg.LinearRegionItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Plot widget
        self._gfx = pg.GraphicsLayoutWidget()
        self._gfx.setBackground("#1e1e1e")
        layout.addWidget(self._gfx, stretch=1)

        # Single plot spanning full width
        self._plot = self._gfx.addPlot(row=0, col=0)
        self._plot.setLabel("bottom", "Time", units="s")
        self._plot.setLabel("left", "Gyro", units="deg/s")
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.getAxis("bottom").setPen("#888")
        self._plot.getAxis("left").setPen("#888")
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideButtons()

        # Create 3 curves (roll, pitch, yaw) – no in-plot legend
        for i in range(3):
            curve = self._plot.plot(
                pen=pg.mkPen(self.AXIS_COLORS[i], width=1),
            )
            self._curves.append(curve)

        # Fixed legend row below the plot
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(8, 0, 8, 2)
        legend_row.addStretch()
        self._legend_labels: list[QLabel] = []
        for i in range(3):
            swatch = QLabel()
            swatch.setFixedSize(14, 3)
            swatch.setStyleSheet(
                f"background: {self.AXIS_COLORS[i]}; border: none;"
            )
            legend_row.addWidget(swatch)
            lbl = QLabel(self.AXIS_NAMES[i])
            lbl.setStyleSheet("color: #ccc; font-size: 11px; border: none;")
            self._legend_labels.append(lbl)
            legend_row.addWidget(lbl)
            if i < 2:
                legend_row.addSpacing(12)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # Draggable region – only the start/end handles can be moved
        # (movable=False prevents dragging the whole region)
        self._region = pg.LinearRegionItem(
            values=[0, 1],
            brush=pg.mkBrush(100, 100, 200, 40),
            pen=pg.mkPen("#aaaaff", width=2),
            hoverBrush=pg.mkBrush(100, 100, 200, 60),
            hoverPen=pg.mkPen("#ccccff", width=2),
            movable=False,
        )
        # Make edge handles individually movable with a larger grab area
        for line in self._region.lines:
            line.setMovable(True)
            line.addMarker("^", position=0.5, size=12)
        self._region.sigRegionChangeFinished.connect(self._on_region_changed)
        self._plot.addItem(self._region)

        # Placeholder text
        self._placeholder = pg.TextItem(
            self.tr("Select a log to preview gyro data"),
            color="#666",
            anchor=(0.5, 0.5),
        )
        self._placeholder.setFont(pg.QtGui.QFont("Segoe UI", 12))
        self._plot.addItem(self._placeholder)
        self._placeholder.setPos(0, 0)

    def show_entry(self, entry: LogEntry | None):
        """Display gyro data for the given log entry."""
        self._entry = entry

        if entry is None:
            for c in self._curves:
                c.setData([], [])
            self._region.setRegion([0, 1])
            self._region.hide()
            self._placeholder.show()
            return

        self._placeholder.hide()

        time_s, gyro_r, gyro_p, gyro_y = entry.gyro_arrays()
        if len(time_s) == 0:
            return

        # Downsample for fast rendering if needed
        max_pts = 20000
        if len(time_s) > max_pts:
            step = len(time_s) // max_pts
            time_s = time_s[::step]
            gyro_r = gyro_r[::step]
            gyro_p = gyro_p[::step]
            gyro_y = gyro_y[::step]

        self._curves[0].setData(time_s, gyro_r)
        self._curves[1].setData(time_s, gyro_p)
        self._curves[2].setData(time_s, gyro_y)

        # Set region to current entry's range
        self._region.blockSignals(True)
        self._region.setRegion([entry.time_start_s, entry.time_end_s])
        self._region.setBounds([0, entry.duration_s])
        self._region.blockSignals(False)
        self._region.show()

        self._plot.enableAutoRange()

    def _on_region_changed(self):
        if self._entry is None:
            return
        lo, hi = self._region.getRegion()
        lo = max(0.0, lo)
        hi = min(self._entry.duration_s, hi)
        self._entry.time_start_s = lo
        self._entry.time_end_s = hi
        self.time_range_changed.emit(lo, hi)

    def clear_preview(self):
        """Reset to empty state."""
        self.show_entry(None)

    def apply_theme(self, t: Theme):
        """Update colors to match the given theme."""
        self._gfx.setBackground(t.plot_bg)
        self._plot.getAxis("bottom").setPen(t.plot_axis)
        self._plot.getAxis("left").setPen(t.plot_axis)
        self._plot.showGrid(x=True, y=True, alpha=t.plot_grid_alpha)
        self._placeholder.setColor(t.fg_dim)
        for lbl in self._legend_labels:
            lbl.setStyleSheet(f"color: {t.fg_dim}; font-size: 11px; border: none;")
