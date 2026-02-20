"""Application entry point for the PyBox GUI."""

from __future__ import annotations

import argparse
import sys


def run():
    """Launch the PyBox GUI application.

    Supports ``--lang <code>`` to override the UI language, e.g.::

        pybox-gui --lang de
    """
    parser = argparse.ArgumentParser(description="PyBox GUI", add_help=False)
    parser.add_argument("--lang", default=None, help="UI language code (e.g. de, en)")
    args, remaining = parser.parse_known_args()

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont

    app = QApplication(remaining)
    app.setApplicationName("PyBox")
    app.setApplicationVersion("0.1.0")

    # Install translations before creating any widgets
    from pybox.gui import settings
    from pybox.gui.i18n import install as install_l10n
    lang = args.lang or settings.language() or None
    install_l10n(lang)

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    from pybox.gui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
