"""Gyro preview plot with draggable start/end time region for epoch selection."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
import numpy as np
import pyqtgraph as pg

from pybox.gui.models import LogEntry


class GyroPreviewWidget(pg.GraphicsLayoutWidget):
    """Shows gyro traces for the currently selected log with a draggable
    LinearRegionItem to set the analysis time range."""

    time_range_changed = pyqtSignal(float, float)  # (start_s, end_s)

    AXIS_COLORS = ["#ff6666", "#66ff66", "#6688ff"]  # Roll, Pitch, Yaw
    AXIS_NAMES = ["Roll", "Pitch", "Yaw"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#1e1e1e")
        self.setMinimumHeight(180)

        self._entry: LogEntry | None = None
        self._curves: list[pg.PlotDataItem] = []
        self._region: pg.LinearRegionItem | None = None

        # Single plot spanning full width
        self._plot = self.addPlot(row=0, col=0)
        self._plot.setLabel("bottom", "Time", units="s")
        self._plot.setLabel("left", "Gyro", units="deg/s")
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.getAxis("bottom").setPen("#888")
        self._plot.getAxis("left").setPen("#888")

        # Legend
        self._legend = self._plot.addLegend(
            offset=(-10, 10),
            labelTextColor="#ccc",
            labelTextSize="10pt",
        )

        # Create 3 curves (roll, pitch, yaw)
        for i in range(3):
            curve = self._plot.plot(
                pen=pg.mkPen(self.AXIS_COLORS[i], width=1),
                name=self.AXIS_NAMES[i],
            )
            self._curves.append(curve)

        # Draggable region
        self._region = pg.LinearRegionItem(
            values=[0, 1],
            brush=pg.mkBrush(100, 100, 200, 40),
            pen=pg.mkPen("#aaaaff", width=2),
            hoverBrush=pg.mkBrush(100, 100, 200, 60),
            hoverPen=pg.mkPen("#ccccff", width=2),
        )
        self._region.sigRegionChangeFinished.connect(self._on_region_changed)
        self._plot.addItem(self._region)

        # Placeholder text
        self._placeholder = pg.TextItem(
            "Select a log to preview gyro data",
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
