# PyBox – Betaflight Blackbox Log Analyzer

A pure-Python tool for decoding and analyzing Betaflight Blackbox flight logs,
inspired by [PIDtoolbox](https://github.com/bw1129/PIDtoolbox).

## Features

- **Native binary decoder** – reads `.bbl` / `.bfl` / `.txt` blackbox logs directly (no external `blackbox_decode` needed)
- **Multi-log support** – a single file can contain multiple flight logs (one per arm cycle)
- **Rich analysis** – PID error, spectral analysis (FFT / PSD), step-response estimation, stick statistics, filter-delay estimation
- **DataFrame output** – decoded data is returned as `pandas.DataFrame` for easy post-processing
- **CLI** – command-line interface for quick decoding and analysis
- **Standalone executable** – can be packaged with PyInstaller for distribution

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev,cli]"

# Decode a blackbox log to CSV
pybox decode samples/btfl_001.bbl

# Run tests
pytest
```

## Project Structure

```
src/pybox/
  decoder/          # Binary format decoder
    stream.py       # Bit-level binary stream reader
    decoders.py     # Variable-byte, Elias, Tag encodings
    headers.py      # Header parser (field defs, sys config)
    frames.py       # Frame parser (I/P/G/H/S/E frames + predictors)
    flightlog.py    # High-level API: load file → DataFrames
  analysis/         # Signal processing & analytics
    pid_error.py    # PID error distributions & vs stick
    spectral.py     # FFT, PSD, throttle-vs-frequency spectrograms
    step_response.py# Step-response deconvolution
    statistics.py   # Stick distributions, motor stats, rate curves
    filters.py      # Filter delay / phase-shift estimation
  units.py          # Unit conversions (gyro→deg/s, vbat→V, …)
  cli.py            # Click-based CLI entry point
tests/              # pytest test suite
samples/            # Example .bbl files for testing
```

## License

GPLv3
