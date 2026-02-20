# PyBox – Betaflight Blackbox Log Analyzer

[![CI – Test & Build](https://github.com/Master92/PyBox/actions/workflows/ci.yml/badge.svg)](https://github.com/Master92/PyBox/actions/workflows/ci.yml)

A pure-Python tool for decoding and analyzing Betaflight Blackbox flight logs,
inspired by [PIDtoolbox](https://github.com/bw1129/PIDtoolbox).

## Features

### Decoder
- **Native binary decoder** – reads `.bbl` / `.bfl` / `.txt` blackbox logs directly (no external `blackbox_decode` needed)
- **Multi-log support** – a single file can contain multiple flight logs (one per arm cycle)
- **DataFrame output** – decoded data is returned as `pandas.DataFrame` for easy post-processing

### Analysis
- **Step-response estimation** – Wiener deconvolution of setpoint → gyro, with smoothed mean curves and ±1σ confidence bands
- **PID error** – error distributions and error-vs-stick analysis
- **Spectral analysis** – FFT, PSD, throttle-vs-frequency spectrograms
- **Statistics** – stick distributions, motor stats, rate curves
- **Filter delay** – phase-shift estimation for gyro filters

### GUI (`pybox-gui`)
- **Load & compare** multiple logs side-by-side with per-log color coding
- **Gyro preview** with draggable time-range selector and smart auto-detection of active flight segments
- **Step response plots** (Roll / Pitch / Yaw) with overlaid mean curves for direct comparison
- **PIDFF config table** showing PID gains for every loaded log
- **Dark / Light theme** toggle (View menu)
- **Runtime language switching** (Language menu) – ships with English and German
- **About dialog** with version and license info
- **Delete individual logs** from the sidebar (✕ button)

### CLI
- **Command-line interface** for quick decoding and analysis
- **Standalone executable** – can be packaged with PyInstaller for distribution

## Installation

```bash
# Core library only
pip install -e .

# With CLI support
pip install -e ".[cli]"

# With GUI support
pip install -e ".[gui]"

# Full development environment (tests, building, CLI, GUI)
pip install -e ".[dev,cli,gui]"
```

**Requirements:** Python ≥ 3.10

## Usage

### GUI

```bash
pybox-gui
```

Optional flags:
- `--lang de` – start with German UI (or any supported locale)

### CLI

```bash
# Decode a blackbox log to CSV
pybox decode samples/btfl_001.bbl
```

## Development

```bash
# Run the test suite
pytest

# Run with coverage
pytest --cov=pybox --cov-report=html

# Compile translation files (.ts → .qm)
python scripts/compile_translations.py

# Build standalone executable
pyinstaller pybox.spec
```

### Adding a new translation

1. Copy `src/pybox/gui/translations/pybox_de.ts` → `pybox_XX.ts`
2. Translate the `<translation>` elements
3. Run `python scripts/compile_translations.py`
4. Add the locale code to `_LANG_NAMES` in `src/pybox/gui/main_window.py`

## Project Structure

```
src/pybox/
  decoder/               # Binary format decoder
    stream.py            # Bit-level binary stream reader
    decoders.py          # Variable-byte, Elias, Tag encodings
    headers.py           # Header parser (field defs, sys config)
    frames.py            # Frame parser (I/P/G/H/S/E frames + predictors)
    flightlog.py         # High-level API: load file → DataFrames
  analysis/              # Signal processing & analytics
    step_response.py     # Step-response deconvolution (Wiener)
    pid_error.py         # PID error distributions
    spectral.py          # FFT, PSD, spectrograms
    statistics.py        # Stick/motor/rate statistics
    filters.py           # Filter delay / phase-shift estimation
  gui/                   # PyQt6 graphical interface
    app.py               # Entry point (pybox-gui)
    main_window.py       # Main window layout & signal wiring
    log_panel.py         # Sidebar: load, list, delete logs
    gyro_preview.py      # Gyro preview plot with range selector
    step_plots.py        # Step response plots + PIDFF table
    models.py            # LogEntry, PIDFFConfig, active-range detection
    theme.py             # Dark / Light theme definitions
    i18n.py              # Internationalization (QTranslator management)
    translations/        # .ts source files + compiled .qm
  units.py               # Unit conversions (gyro→deg/s, vbat→V, …)
  cli.py                 # Click-based CLI entry point
scripts/
  compile_translations.py  # Pure-Python .ts → .qm compiler
tests/                   # pytest test suite
samples/                 # Example .bbl files for testing
```

## CI

GitHub Actions runs on every push and PR:
- **Test** – `pytest` on Ubuntu, macOS, and Windows (Python 3.12)
- **Build** – PyInstaller executables for all three platforms

## License

This project is licensed under the **GNU General Public License v3.0** – see the [LICENSE](LICENSE) file for details.
