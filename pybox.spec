# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for building PyBox as a standalone executable.

Usage:
    pyinstaller pybox.spec

This produces a single-file executable in dist/pybox.exe (Windows)
or dist/pybox (Linux/macOS).
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/pybox/cli.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pybox',
        'pybox.decoder',
        'pybox.decoder.stream',
        'pybox.decoder.decoders',
        'pybox.decoder.defs',
        'pybox.decoder.headers',
        'pybox.decoder.frames',
        'pybox.decoder.flightlog',
        'pybox.analysis',
        'pybox.analysis.pid_error',
        'pybox.analysis.spectral',
        'pybox.analysis.step_response',
        'pybox.analysis.statistics',
        'pybox.analysis.filters',
        'pybox.units',
        'click',
        'numpy',
        'pandas',
        'scipy',
        'scipy.signal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pybox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
