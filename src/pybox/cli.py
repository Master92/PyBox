"""PyBox CLI – command-line interface for decoding and analyzing Blackbox logs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from pybox import __version__


@click.group()
@click.version_option(__version__, prog_name="pybox")
def main():
    """PyBox – Betaflight Blackbox log decoder and analysis tool."""


# ── decode ────────────────────────────────────────────────────────────

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--index", "-i", default=-1, type=int, help="Log index to decode (-1 = all)")
@click.option("--output", "-o", default=None, type=click.Path(), help="Output CSV path (default: <input>.csv)")
@click.option("--raw", is_flag=True, help="Don't apply predictions (raw field deltas)")
def decode(input_file: str, index: int, output: str | None, raw: bool):
    """Decode a Blackbox log file to CSV."""
    from pybox.decoder.flightlog import FlightLog

    path = Path(input_file)
    log = FlightLog(path)
    click.echo(f"Found {log.log_count} log(s) in {path.name}")

    indices = range(log.log_count) if index < 0 else [index]

    for idx in indices:
        click.echo(f"\nDecoding log {idx + 1}/{log.log_count}...")
        decoded = log.decode(idx, raw=raw)
        df = decoded.to_dataframe()

        if output and len(indices) == 1:
            out_path = Path(output)
        else:
            suffix = f".{idx + 1:02d}.csv"
            out_path = path.with_suffix(suffix)

        df.to_csv(out_path, index=False)
        click.echo(f"  → {out_path} ({len(df)} frames, {decoded.duration_s:.1f}s, {decoded.sample_rate_hz:.0f} Hz)")
        click.echo(f"  Valid: {decoded.valid_frame_count}, Corrupt: {decoded.corrupt_frame_count}")


# ── info ──────────────────────────────────────────────────────────────

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--index", "-i", default=0, type=int, help="Log index (default: 0)")
def info(input_file: str, index: int):
    """Show log metadata and setup info."""
    from pybox.decoder.flightlog import FlightLog

    path = Path(input_file)
    log = FlightLog(path)
    click.echo(f"File: {path.name}")
    click.echo(f"Logs: {log.log_count}")

    header = log.get_header(index)
    click.echo(f"\n--- Log {index + 1} ---")
    click.echo(f"Firmware: {header.firmware_revision}")
    click.echo(f"FC Version: {header.fc_version}")
    click.echo(f"Data Version: {header.data_version}")
    click.echo(f"Firmware Type: {header.sys_config.firmware_type.name}")

    i_def = header.frame_defs.get(ord("I"))
    if i_def:
        click.echo(f"Fields ({i_def.field_count}): {', '.join(i_def.field_names)}")

    click.echo(f"\nSystem Config:")
    sc = header.sys_config
    click.echo(f"  minthrottle:    {sc.minthrottle}")
    click.echo(f"  maxthrottle:    {sc.maxthrottle}")
    click.echo(f"  motorOutput:    {sc.motor_output_low} – {sc.motor_output_high}")
    click.echo(f"  rcRate:         {sc.rc_rate}")
    click.echo(f"  gyroScale:      {sc.gyro_scale:.10f}")
    click.echo(f"  acc_1G:         {sc.acc_1g}")
    click.echo(f"  vbatscale:      {sc.vbatscale}")
    click.echo(f"  vbatref:        {sc.vbatref}")

    click.echo(f"\nAll Headers:")
    for key, val in sorted(header.raw_headers.items()):
        click.echo(f"  {key}: {val}")


# ── analyze ───────────────────────────────────────────────────────────

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--index", "-i", default=0, type=int, help="Log index (default: 0)")
@click.option("--output", "-o", default=None, type=click.Path(), help="Output JSON path")
def analyze(input_file: str, index: int, output: str | None):
    """Run analysis on a decoded log (PID error, statistics, spectral)."""
    import numpy as np

    from pybox.decoder.flightlog import FlightLog
    from pybox.analysis.statistics import compute_flight_statistics

    path = Path(input_file)
    log = FlightLog(path)
    decoded = log.decode(index)
    df = decoded.to_dataframe()

    click.echo(f"Log {index + 1}: {decoded.valid_frame_count} frames, {decoded.duration_s:.1f}s, {decoded.sample_rate_hz:.0f} Hz")

    # Flight statistics
    stats = compute_flight_statistics(
        df,
        motor_output_low=decoded.header.sys_config.motor_output_low,
        motor_output_high=decoded.header.sys_config.motor_output_high,
    )

    click.echo(f"\n--- Flight Statistics ---")
    click.echo(f"Duration: {stats.duration_s:.1f} s")
    click.echo(f"Sample Rate: {stats.sample_rate_hz:.0f} Hz")

    for sd in stats.stick_distributions:
        click.echo(f"  {sd.axis}: mean={sd.mean_percent:.1f}%, std={sd.std_percent:.1f}%")

    if stats.motor_stats is not None:
        click.echo(f"  Motor means: {', '.join(f'{m:.1f}%' for m in stats.motor_stats.mean_percent)}")

    # PID error analysis
    from pybox.analysis.pid_error import analyze_pid_errors
    pid_results = analyze_pid_errors(df)
    if pid_results:
        click.echo(f"\n--- PID Error ---")
        for r in pid_results:
            click.echo(f"  {r.axis}: std={r.std_dev:.2f}")

    # Save to JSON if requested
    if output:
        result = {
            "file": str(path),
            "log_index": index,
            "duration_s": stats.duration_s,
            "sample_rate_hz": stats.sample_rate_hz,
            "firmware": decoded.header.firmware_revision,
            "fc_version": decoded.header.fc_version,
            "valid_frames": decoded.valid_frame_count,
            "corrupt_frames": decoded.corrupt_frame_count,
            "stick_distributions": {
                sd.axis: {"mean": sd.mean_percent, "std": sd.std_percent}
                for sd in stats.stick_distributions
            },
            "pid_error": {
                r.axis: {"std": r.std_dev}
                for r in pid_results
            },
        }
        if stats.motor_stats is not None:
            result["motor_stats"] = {
                "mean_percent": stats.motor_stats.mean_percent.tolist(),
                "std_percent": stats.motor_stats.std_percent.tolist(),
            }

        out_path = Path(output)
        out_path.write_text(json.dumps(result, indent=2))
        click.echo(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
