"""Internationalization (i18n) support for the PyBox GUI.

Uses Qt's QTranslator system.  Translation files live in
``src/pybox/gui/translations/`` as ``.ts`` (source) and ``.qm`` (compiled).

Workflow for translators
------------------------
1. Mark all user-visible strings with ``self.tr("…")`` in QWidget subclasses
   or ``QCoreApplication.translate("Context", "…")`` elsewhere.
2. Run  ``pylupdate6 src/pybox/gui/*.py -ts src/pybox/gui/translations/pybox_de.ts``
   (repeat for each locale).
3. Edit the ``.ts`` file (e.g. with Qt Linguist or a text editor).
4. Compile:  ``lrelease src/pybox/gui/translations/pybox_de.ts``
5. The application picks up the ``.qm`` automatically at startup.

At runtime
----------
Call ``install(locale_code)`` **before** creating any widgets.
``locale_code`` can be ``"de"``, ``"en"``, ``"fr"`` etc.
If no ``.qm`` is found for the requested locale the app falls back to English
(i.e. the source strings are used as-is).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTranslator, QLocale, QCoreApplication, QLibraryInfo

# Directory that holds the compiled .qm files
_TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"

# Keep references so they are not garbage-collected
_translators: list[QTranslator] = []


def available_locales() -> list[str]:
    """Return locale codes for which a compiled .qm file exists."""
    if not _TRANSLATIONS_DIR.is_dir():
        return []
    codes: list[str] = []
    for f in sorted(_TRANSLATIONS_DIR.glob("pybox_*.qm")):
        # e.g. pybox_de.qm  →  "de"
        code = f.stem.replace("pybox_", "")
        codes.append(code)
    return codes


def install(locale_code: Optional[str] = None) -> bool:
    """Install a translator for *locale_code* into the running QApplication.

    If *locale_code* is ``None``, the system locale is used.
    Returns ``True`` if a matching ``.qm`` file was loaded.

    Must be called **after** ``QApplication()`` is created but **before**
    any translatable widgets are instantiated.
    """
    app = QCoreApplication.instance()
    if app is None:
        return False

    if locale_code is None:
        locale_code = QLocale.system().name()[:2]  # e.g. "de_DE" → "de"

    # Try to load Qt's own translations (buttons, dialogs, etc.)
    qt_translator = QTranslator()
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_translator.load(f"qtbase_{locale_code}", qt_translations_path):
        app.installTranslator(qt_translator)
        _translators.append(qt_translator)

    # Load our application translations
    translator = QTranslator()
    qm_path = _TRANSLATIONS_DIR / f"pybox_{locale_code}.qm"
    if qm_path.is_file() and translator.load(str(qm_path)):
        app.installTranslator(translator)
        _translators.append(translator)
        return True

    return False
