"""Application entry point for the PyBox GUI."""

from __future__ import annotations

import sys


def run():
    """Launch the PyBox GUI application."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont

    app = QApplication(sys.argv)
    app.setApplicationName("PyBox")
    app.setApplicationVersion("0.1.0")

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    from pybox.gui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
