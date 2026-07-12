#!/usr/bin/env python3
"""
plot.py

General-purpose plotting utility for CSV datasets.

Core design pattern:
    parse_args -> build_config -> validate_config -> run_workflow

Mental model:
    Config        = typed mission order for this run
    OutputPaths   = artifact map for this run
    validate_*    = gates before trust
    process_*     = turn raw input into plot-ready signal
    save_*        = preserve evidence as files

Operator rule:
    CSV input is untrusted text until columns and types are validated.

Examples:
    # One line plot, one y-column.
    python3 plot.py --input data.csv --x-column time_s --y-columns raw_signal

    # One line plot, multiple y-columns.
    python3 plot.py --input data.csv --x-column time_s --y-columns command response raw_signal

    # Multiple plot families from the same data.
    python3 plot.py --input data.csv --plot-type line scatter histogram --x-column time_s --y-columns raw_signal

    # Light background, if needed for docs/slides.
    python3 plot.py --input data.csv --theme light
"""

from __future__ import annotations

# =============================================================================
# S0. Metadata
# =============================================================================

VERSION = "3.0.0"
AUTHOR = "V Halcyon"


# =============================================================================
# S1. Imports
# =============================================================================

import argparse
import csv
import json
import logging
import math
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

# Use a non-interactive backend so saving plots works in terminals/headless runs.
# This must happen before importing pyplot.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


# =============================================================================
# S2. Constants / defaults
# =============================================================================

# Keep defaults explicit and easy to edit. Use expanduser() for ~ paths.
DEFAULT_INPUT_PATH = None
DEFAULT_OUTPUT_DIR = Path("~/Vec/Engineering/logs/python/output/").expanduser()

VALID_PLOT_TYPES = ["line", "scatter", "histogram"]
VALID_THEMES = ["halcyon-dark", "dark", "light"]


# =============================================================================
# S3. Data models
# =============================================================================

@dataclass(frozen=True)
class Config:
    """
    Typed run configuration.

    Think of Config as the run's mission order. Once built, everything else
    should receive Config instead of reaching back into argparse directly.
    frozen=True makes accidental mutation harder.
    """

    input_path: Path | None
    output_dir: Path
    sample_rate_hz: float
    no_load_run: bool
    verbose: bool
    plot_types: list[str]
    x_column: str
    y_columns: list[str]
    title: str | None
    xlabel: str | None
    ylabel: str | None
    theme: str
    fig_width: float
    fig_height: float
    dpi: int
    hist_bins: int
    output_stem: str | None
    coerce_numeric: bool
    self_test: bool
    run_id: str


@dataclass(frozen=True)
class OutputPaths:
    """
    Standard artifact locations for one run.

    Keep path construction centralized. This avoids bugs where one function
    writes to ./output while another writes to ~/Engineering/.../output.
    """

    root: Path
    logs: Path
    tables: Path
    figures: Path

    @classmethod
    def from_config(cls, config: Config) -> "OutputPaths":
        return cls(
            root=config.output_dir,
            logs=config.output_dir / "logs",
            tables=config.output_dir / "tables",
            figures=config.output_dir / "figures",
        )


# =============================================================================
# S4. Logging / run identity
# =============================================================================

def utc_run_id() -> str:
    """Return a timestamp safe for filenames and artifact IDs."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def setup_logging(verbose: bool) -> None:
    """
    Configure script logging.

    INFO is for normal operator status.
    DEBUG is for investigation detail.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


log = logging.getLogger("plot")


# =============================================================================
# S5. Path + filesystem helpers
# =============================================================================

def expand_path(path: Path | str | None) -> Path | None:
    """
    Expand ~ and return an absolute path, even if the target does not exist yet.

    strict=False means this works before output directories/files are created.
    Use this at config boundaries so the rest of the script has stable paths.
    """
    if path is None:
        return None
    return Path(path).expanduser().resolve(strict=False)


def ensure_dir(path: Path, *, no_load_run: bool = False) -> None:
    """
    Ensure a directory exists.

    Important:
        pass a directory path here, not a file path.
        For a file output path, call ensure_dir(output_file.parent).
    """
    if no_load_run:
        log.info("[NO-LOAD] mkdir -p %s", path)
        return

    path.mkdir(parents=True, exist_ok=True)


def ensure_output_dirs(paths: OutputPaths, *, no_load_run: bool = False) -> None:
    """Create the standard artifact directories for this run."""
    for path in [paths.root, paths.logs, paths.tables, paths.figures]:
        ensure_dir(path, no_load_run=no_load_run)


def safe_filename(text: str, *, max_len: int = 80) -> str:
    """
    Convert a title/string into something safe for filenames.

    Example:
        "Command vs response" -> "command_vs_response"
    """
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text[:max_len] or "artifact"


def backup_if_exists(path: Path, run_id: str, *, no_load_run: bool = False) -> Path | None:
    """
    Rename an existing file before overwriting it.

    Use when rerunning a script could destroy useful evidence.
    """
    if not path.exists():
        return None

    backup_path = path.with_name(f"{path.name}.bak.{run_id}")

    if no_load_run:
        log.info("[NO-LOAD] backup %s -> %s", path, backup_path)
    else:
        path.replace(backup_path)
        log.info("Backed up %s -> %s", path, backup_path)

    return backup_path


# =============================================================================
# S6. Text / JSON / CSV artifact helpers
# =============================================================================

def atomic_write_text(path: Path, text: str, *, no_load_run: bool = False) -> None:
    """
    Write text through a temporary file, then replace the target.

    This lowers the chance of leaving a half-written artifact if the script
    crashes during write.
    """
    ensure_dir(path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] write text %s", path)
        return

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    log.info("Wrote %s", path)


def write_json(path: Path, payload: dict, *, no_load_run: bool = False) -> None:
    """Write a dictionary as pretty JSON."""
    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    atomic_write_text(path, text, no_load_run=no_load_run)


def write_csv_dicts(
    path: Path,
    rows: Iterable[dict],
    fieldnames: Sequence[str],
    *,
    no_load_run: bool = False,
) -> None:
    """Write a list/iterable of dictionaries to CSV."""
    ensure_dir(path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] write CSV %s", path)
        return

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    log.info("Wrote %s", path)


def write_dataframe_csv(df: pd.DataFrame, path: Path, *, no_load_run: bool = False) -> Path:
    """Write a DataFrame to CSV while keeping filesystem behavior consistent."""
    ensure_dir(path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] write DataFrame CSV %s shape=%s", path, df.shape)
        return path

    df.to_csv(path, index=False)
    log.info("Wrote %s shape=%s", path, df.shape)
    return path


# =============================================================================
# S7. Input loading + dataframe validation helpers
# =============================================================================

def load_csv_dataframe(path: Path) -> pd.DataFrame:
    """
    Load CSV input as a DataFrame.

    Boundary rule:
        CSV is untrusted text until columns/types are validated.
    """
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")

    if path.is_dir():
        raise ValueError(f"Input path is a directory; expected a file: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError(f"Unsupported input type {path.suffix!r}; expected .csv")

    df = pd.read_csv(path)
    log.info("Loaded %s shape=%s", path, df.shape)
    return df



def make_synthetic_dataset(*, sample_rate_hz: float = 10.0, seconds: float = 20.0) -> pd.DataFrame:
    """Create deterministic demo data so plot.py runs on a fresh laptop."""
    n = max(2, int(sample_rate_hz * seconds))
    time_s = [i / sample_rate_hz for i in range(n)]
    command = [1.0 if t >= 2.0 else 0.0 for t in time_s]
    response = [1.0 - math.exp(-max(t - 2.0, 0.0) / 4.0) for t in time_s]
    raw_signal = [r + 0.03 * math.sin(2.0 * math.pi * 0.7 * t) for t, r in zip(time_s, response)]
    return pd.DataFrame({
        "time_s": time_s,
        "command": command,
        "response": response,
        "raw_signal": raw_signal,
    })


def normalize_columns(columns: str | Sequence[str]) -> list[str]:
    """
    Accept one column name or many column names.

    Why this exists:
        Strings are iterable in Python.
        list("raw_signal") becomes ["r", "a", "w", ...]
        We do NOT want that behavior for column names.

    Valid:
        "raw_signal"
        ["command", "response"]

    Invalid:
        [["raw_signal"]]
    """
    if isinstance(columns, str):
        return [columns]

    normalized = list(columns)

    for col in normalized:
        if not isinstance(col, str):
            raise TypeError(
                f"Column names must be strings. Got {col!r} of type {type(col).__name__}. "
                "Did you accidentally pass a list inside a list?"
            )

    return normalized


def unique_preserve_order(items: Sequence[str]) -> list[str]:
    """
    Remove duplicates without changing order.

    Avoids repeated numeric coercion when x also appears in y_columns.
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def require_columns(df: pd.DataFrame, columns: str | Sequence[str]) -> None:
    """
    Confirm that the DataFrame contains all required columns.

    This intentionally avoids set(required), because nested lists produce
    "unhashable type: 'list'". We validate each item as a string first.
    """
    required = normalize_columns(columns)
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def coerce_numeric_columns(df: pd.DataFrame, columns: str | Sequence[str]) -> pd.DataFrame:
    """
    Convert columns to numeric dtype for plotting/math.

    CSV values often arrive as strings. Matplotlib may treat string numbers as
    categorical labels, causing weird axes and warnings. This gate converts
    signal columns into real numeric values and fails if conversion creates NaN.
    """
    normalized = normalize_columns(columns)
    out = df.copy()
    require_columns(out, normalized)

    for col in normalized:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    bad_mask = out[normalized].isna().any(axis=1)
    if bad_mask.any():
        bad_rows = out.loc[bad_mask, normalized].head(10)
        raise ValueError(
            "Non-numeric values found after conversion. "
            f"First bad rows:\n{bad_rows}"
        )

    return out


def data_quality_summary(df: pd.DataFrame) -> dict:
    """
    Produce a compact machine-readable data quality summary.

    This becomes useful later when comparing logs across runs.
    """
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_by_column": {col: int(df[col].isna().sum()) for col in df.columns},
    }


def safe_float(value: object, default: float = math.nan) -> float:
    """Convert a value to float; return default if conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def numeric_stats(df: pd.DataFrame, columns: Sequence[str]) -> dict:
    """Return simple numeric stats for requested columns when available."""
    stats: dict[str, dict[str, float]] = {}
    for col in normalize_columns(columns):
        if col not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        stats[col] = {
            "min": safe_float(df[col].min()),
            "max": safe_float(df[col].max()),
            "mean": safe_float(df[col].mean()),
            "std": safe_float(df[col].std()),
        }
    return stats


# =============================================================================
# S8. Plot style / theme helpers
# =============================================================================

def apply_plot_theme(fig: plt.Figure, ax: plt.Axes, theme: str) -> None:
    """
    Apply plot aesthetics at the axis/figure level.

    Dark-background saving rule:
        It is not enough to make the axis dark on screen. When saving, also pass
        facecolor=fig.get_facecolor() to fig.savefig(...). The save helpers do
        that for you.
    """
    if theme == "light":
        ax.grid(True, alpha=0.3)
        return

    # Halcyon / black-amber defaults.
    if theme == "halcyon-dark":
        bg = "#07090D"       # near-black page
        panel = "#282829"    # cockpit panel
        text = "#F2E8D5"     # warm bone text
        spine = "#B88746"    # aged brass
        grid = "#7A653E"     # dim amber grid
        colors = [
            "#B7410E",  # rust
            "#FFBF00",  # amber
            "#C97C5D",  # copper
            "#8FA37A",  # muted moss
            "#76B7B2",  # oxidized teal
            "#A77BD4",  # low violet
        ]
    else:
        bg = "#0B0D10"
        panel = "#141820"
        text = "#E8E8E8"
        spine = "#A0A0A0"
        grid = "#5A5A5A"
        colors = ["#B7410E", "#8FA37A", "#E6C978", "#4FA3B8"]

    fig.patch.set_facecolor(bg)
    ax.set_facecolor(panel)
    ax.set_prop_cycle(color=colors)

    ax.title.set_color(text)
    ax.xaxis.label.set_color(text)
    ax.yaxis.label.set_color(text)
    ax.tick_params(axis="x", colors=text)
    ax.tick_params(axis="y", colors=text)

    for side in ["top", "right", "bottom", "left"]:
        ax.spines[side].set_color(spine)

    ax.grid(True, color=grid, alpha=0.28, linewidth=0.8)

    legend = ax.get_legend()
    if legend is not None:
        legend.get_frame().set_facecolor(panel)
        legend.get_frame().set_edgecolor(spine)
        for label in legend.get_texts():
            label.set_color(text)


def save_figure(fig: plt.Figure, output_path: Path, *, dpi: int, theme: str) -> Path:
    """
    Save a Matplotlib figure while preserving dark backgrounds.

    facecolor=fig.get_facecolor() is the key line for dark-background PNGs.
    """
    fig.savefig(
        output_path,
        dpi=dpi,
        facecolor=fig.get_facecolor() if theme != "light" else "white",
        bbox_inches="tight",
    )
    plt.close(fig)
    log.info("Wrote figure %s", output_path)
    return output_path


# =============================================================================
# S9. Plot helpers
# =============================================================================

def save_line_plot(
    df: pd.DataFrame,
    *,
    x: str,
    y_columns: str | Sequence[str],
    output_path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    theme: str,
    fig_size: tuple[float, float],
    dpi: int,
    no_load_run: bool = False,
) -> Path:
    """
    Save a line plot.

    x:
        One column name for the x-axis.

    y_columns:
        One column name OR multiple column names.
        Both are valid:
            y_columns="raw_signal"
            y_columns=["command", "response"]
    """
    y_columns = normalize_columns(y_columns)
    require_columns(df, [x, *y_columns])
    ensure_dir(output_path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] save line plot %s", output_path)
        return output_path

    fig, ax = plt.subplots(figsize=fig_size)
    apply_plot_theme(fig, ax, theme)

    for col in y_columns:
        ax.plot(df[x], df[col], label=col, linewidth=1.8)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    apply_plot_theme(fig, ax, theme)  # Apply again so legend inherits dark styling.

    fig.tight_layout()
    return save_figure(fig, output_path, dpi=dpi, theme=theme)


def save_scatter_plot(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    output_path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    theme: str,
    fig_size: tuple[float, float],
    dpi: int,
    no_load_run: bool = False,
) -> Path:
    """Save a scatter plot for correlation/relationship checks."""
    require_columns(df, [x, y])
    ensure_dir(output_path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] save scatter plot %s", output_path)
        return output_path

    fig, ax = plt.subplots(figsize=fig_size)
    apply_plot_theme(fig, ax, theme)

    ax.scatter(df[x], df[y], s=18, alpha=0.82)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    fig.tight_layout()
    return save_figure(fig, output_path, dpi=dpi, theme=theme)


def save_histogram(
    df: pd.DataFrame,
    *,
    column: str,
    output_path: Path,
    title: str,
    xlabel: str,
    ylabel: str = "Count",
    bins: int = 30,
    theme: str,
    fig_size: tuple[float, float],
    dpi: int,
    no_load_run: bool = False,
) -> Path:
    """Save a histogram for distributions, guard bands, and thresholds."""
    require_columns(df, [column])
    ensure_dir(output_path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] save histogram %s", output_path)
        return output_path

    fig, ax = plt.subplots(figsize=fig_size)
    apply_plot_theme(fig, ax, theme)

    ax.hist(df[column].dropna(), bins=bins, alpha=0.88)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    fig.tight_layout()
    return save_figure(fig, output_path, dpi=dpi, theme=theme)


# =============================================================================
# S10. External command helper
# =============================================================================

def run_command(
    cmd: Sequence[str],
    *,
    no_load_run: bool = False,
    check: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """
    Run a shell command safely without shell=True.

    Use this for controlled external tools. For arbitrary user input, be careful.
    """
    if no_load_run:
        log.info("[NO-LOAD] %s", " ".join(cmd))
        return None

    log.debug("Running command: %s", " ".join(cmd))
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        capture_output=True,
    )


# =============================================================================
# S11. Project-specific workflow hooks
# =============================================================================

def columns_needed_for_plotting(config: Config) -> list[str]:
    """
    Decide which columns must exist for the requested plots.

    Line/scatter need x + y.
    Histogram only needs y.
    """
    needed: list[str] = []

    if "line" in config.plot_types or "scatter" in config.plot_types:
        needed.append(config.x_column)

    needed.extend(config.y_columns)
    return unique_preserve_order(needed)


def process_data(config: Config) -> pd.DataFrame:
    """
    Load, validate, type-convert, and return plot-ready data.

    This is the main place to customize per project later.
    For now, the script is general: it only requires the columns requested by
    the CLI and converts them to numeric unless --no-coerce-numeric is used.
    """
    if config.input_path is None:
        log.warning("No --input provided. Generating synthetic dataset.")
        raw_df = make_synthetic_dataset(sample_rate_hz=config.sample_rate_hz)
    else:
        raw_df = load_csv_dataframe(config.input_path)

    # Gate 1: schema. Do we have the signals we think we have?
    needed_columns = columns_needed_for_plotting(config)
    require_columns(raw_df, needed_columns)

    # Gate 2: numeric conversion. Are signal columns real numbers, not strings?
    if config.coerce_numeric:
        processed_df = coerce_numeric_columns(raw_df, needed_columns)
    else:
        processed_df = raw_df.copy()

    return processed_df


def base_output_stem(config: Config) -> str:
    """Choose a stable artifact stem for this run's figure filenames."""
    if config.output_stem:
        return safe_filename(config.output_stem)
    if config.title:
        return safe_filename(config.title)
    return safe_filename("_".join([config.x_column, *config.y_columns]))


def save_analysis_artifacts(config: Config, paths: OutputPaths, df: pd.DataFrame) -> list[Path]:
    """
    Save artifacts for this run.

    Returns a list of artifact paths so the summary/manifest can say what was produced.
    """
    artifacts: list[Path] = []
    fig_size = (config.fig_width, config.fig_height)
    stem = base_output_stem(config)

    processed_csv = paths.tables / f"processed_{config.run_id}.csv"
    artifacts.append(write_dataframe_csv(df, processed_csv, no_load_run=config.no_load_run))

    if "line" in config.plot_types:
        y_label = config.ylabel or ", ".join(config.y_columns)
        artifacts.append(
            save_line_plot(
                df,
                x=config.x_column,
                y_columns=config.y_columns,
                output_path=paths.figures / f"{config.run_id}_{stem}_line.png",
                title=config.title or f"{', '.join(config.y_columns)} vs {config.x_column}",
                xlabel=config.xlabel or config.x_column,
                ylabel=y_label,
                theme=config.theme,
                fig_size=fig_size,
                dpi=config.dpi,
                no_load_run=config.no_load_run,
            )
        )

    if "scatter" in config.plot_types:
        for y_col in config.y_columns:
            artifacts.append(
                save_scatter_plot(
                    df,
                    x=config.x_column,
                    y=y_col,
                    output_path=paths.figures / f"{config.run_id}_{stem}_scatter_{safe_filename(y_col)}.png",
                    title=config.title or f"{y_col} vs {config.x_column}",
                    xlabel=config.xlabel or config.x_column,
                    ylabel=config.ylabel or y_col,
                    theme=config.theme,
                    fig_size=fig_size,
                    dpi=config.dpi,
                    no_load_run=config.no_load_run,
                )
            )

    if "histogram" in config.plot_types:
        for y_col in config.y_columns:
            artifacts.append(
                save_histogram(
                    df,
                    column=y_col,
                    output_path=paths.figures / f"{config.run_id}_{stem}_histogram_{safe_filename(y_col)}.png",
                    title=config.title or f"Distribution of {y_col}",
                    xlabel=config.xlabel or y_col,
                    ylabel="Count",
                    bins=config.hist_bins,
                    theme=config.theme,
                    fig_size=fig_size,
                    dpi=config.dpi,
                    no_load_run=config.no_load_run,
                )
            )

    return artifacts


def summarize_results(df: pd.DataFrame, artifacts: Sequence[Path], config: Config) -> dict:
    """Create a compact run summary."""
    summary = data_quality_summary(df)
    summary.update(
        {
            "status": "ok" if len(df) else "empty dataset",
            "artifacts": [str(path) for path in artifacts],
            "plot_types": config.plot_types,
            "x_column": config.x_column,
            "y_columns": config.y_columns,
            "numeric_stats": numeric_stats(df, columns_needed_for_plotting(config)),
        }
    )
    return summary


def write_run_manifest(config: Config, paths: OutputPaths) -> None:
    """
    Write run metadata before processing.

    Manifest = evidence about how the run was configured.
    Summary  = evidence about what the run produced.
    """
    manifest = {
        **asdict(config),
        "input_path": str(config.input_path) if config.input_path else None,
        "output_dir": str(config.output_dir),
        "python": sys.version,
        "script_version": VERSION,
        "author": AUTHOR,
        "cwd": str(Path.cwd()),
    }

    write_json(
        paths.logs / f"run_manifest_{config.run_id}.json",
        manifest,
        no_load_run=config.no_load_run,
    )


# =============================================================================
# S12. CLI / configuration
# =============================================================================

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """
    Parse command-line arguments.

    argparse gives raw user intent. build_config turns it into typed state.
    """
    parser = argparse.ArgumentParser(
        description="General-purpose CSV plotting utility with operator-engineer gates."
    )

    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Input CSV/data file. If omitted, a synthetic dataset is generated.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for logs, tables, and figures.",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=float,
        default=10.0,
        help="Nominal sample/logging rate. Used for validation/metadata.",
    )
    parser.add_argument(
        "--no-load-run",
        action="store_true",
        help="Preview actions without writing artifacts.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--plot-type",
        "-p",
        dest="plot_types",
        nargs="+",
        choices=VALID_PLOT_TYPES,
        default=["line"],
        help="One or more plot types: line, scatter, histogram.",
    )
    parser.add_argument(
        "--x-column",
        "--x-data",
        "-x",
        type=str,
        dest="x_column",
        default="time_s",
        help="DataFrame column to plot on the x-axis. Default: time_s.",
    )
    parser.add_argument(
        "--y-columns",
        "--y-data",
        "-y",
        type=str,
        nargs="+",
        dest="y_columns",
        default=["raw_signal"],
        help="One or more DataFrame columns to plot on the y-axis. Example: -y command response raw_signal.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Optional plot title. Auto-generated if omitted.",
    )
    parser.add_argument(
        "--xlabel",
        type=str,
        default=None,
        help="Optional x-axis label. Defaults to x column name.",
    )
    parser.add_argument(
        "--ylabel",
        type=str,
        default=None,
        help="Optional y-axis label. Defaults to y column name(s).",
    )
    parser.add_argument(
        "--theme",
        choices=VALID_THEMES,
        default="halcyon-dark",
        help="Plot theme. Default: halcyon-dark.",
    )
    parser.add_argument(
        "--fig-width",
        type=float,
        default=10.0,
        help="Figure width in inches.",
    )
    parser.add_argument(
        "--fig-height",
        type=float,
        default=5.0,
        help="Figure height in inches.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=160,
        help="Saved figure DPI.",
    )
    parser.add_argument(
        "--hist-bins",
        type=int,
        default=30,
        help="Number of bins for histogram plots.",
    )
    parser.add_argument(
        "--output-stem",
        type=str,
        default=None,
        help="Optional filename stem for output figures.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a smoke test in a temporary directory.",
    )
    parser.add_argument(
        "--no-coerce-numeric",
        action="store_true",
        help="Skip numeric conversion. Use only if you intentionally want categorical/string axes.",
    )

    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    """
    Convert argparse output into a typed Config.

    Path rule:
        Expand/resolve paths here, once. Do not scatter expanduser() everywhere.
    """
    return Config(
        input_path=expand_path(args.input_path),
        output_dir=expand_path(args.output_dir),
        sample_rate_hz=args.sample_rate_hz,
        no_load_run=args.no_load_run,
        verbose=args.verbose,
        plot_types=normalize_columns(args.plot_types),
        x_column=args.x_column,
        y_columns=normalize_columns(args.y_columns),
        title=args.title,
        xlabel=args.xlabel,
        ylabel=args.ylabel,
        theme=args.theme,
        fig_width=args.fig_width,
        fig_height=args.fig_height,
        dpi=args.dpi,
        hist_bins=args.hist_bins,
        output_stem=args.output_stem,
        coerce_numeric=not args.no_coerce_numeric,
        self_test=args.self_test,
        run_id=utc_run_id(),
    )


def validate_config(config: Config) -> None:
    """Validate run configuration before doing work."""
    if config.sample_rate_hz <= 0:
        raise ValueError("--sample-rate-hz must be positive")

    if config.fig_width <= 0 or config.fig_height <= 0:
        raise ValueError("--fig-width and --fig-height must be positive")

    if config.dpi <= 0:
        raise ValueError("--dpi must be positive")

    if config.hist_bins <= 0:
        raise ValueError("--hist-bins must be positive")

    if config.input_path is not None:
        if not config.input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {config.input_path}")

        if config.input_path.is_dir():
            raise ValueError(f"Input path is a directory; expected a file: {config.input_path}")

        if config.input_path.suffix.lower() != ".csv":
            raise ValueError(f"Expected .csv input, got: {config.input_path.suffix}")

    for plot_type in config.plot_types:
        if plot_type not in VALID_PLOT_TYPES:
            raise ValueError(f"Unsupported plot type: {plot_type}. Valid: {VALID_PLOT_TYPES}")

    if config.theme not in VALID_THEMES:
        raise ValueError(f"Unsupported theme: {config.theme}. Valid: {VALID_THEMES}")


# =============================================================================
# S13. Main workflow
# =============================================================================

def run_workflow(config: Config) -> None:
    """
    One readable run sequence.

    Operator flow:
        1. Create artifact dirs
        2. Write manifest
        3. Load/process data
        4. Save artifacts
        5. Write summary
    """
    log.info("Starting workflow")
    log.info("Run ID: %s", config.run_id)

    paths = OutputPaths.from_config(config)
    ensure_output_dirs(paths, no_load_run=config.no_load_run)

    write_run_manifest(config, paths)

    processed_df = process_data(config)
    artifacts = save_analysis_artifacts(config, paths, processed_df)
    summary = summarize_results(processed_df, artifacts, config)

    write_json(
        paths.logs / f"summary_{config.run_id}.json",
        summary,
        no_load_run=config.no_load_run,
    )

    log.info("Summary: %s", summary)
    log.info("Workflow complete")


def run_self_test() -> None:
    """Run a small smoke test in an isolated temporary directory."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="plot_py_vv_") as tmp_dir:
        cfg = Config(
            input_path=None,
            output_dir=Path(tmp_dir) / "output",
            sample_rate_hz=10.0,
            no_load_run=False,
            verbose=True,
            plot_types=["line", "scatter", "histogram"],
            x_column="time_s",
            y_columns=["raw_signal"],
            title="Self Test",
            xlabel=None,
            ylabel=None,
            theme="halcyon-dark",
            fig_width=8.0,
            fig_height=4.0,
            dpi=100,
            hist_bins=20,
            output_stem="self_test",
            coerce_numeric=True,
            self_test=True,
            run_id="SELF_TEST",
        )
        validate_config(cfg)
        run_workflow(cfg)
        expected_dirs = [cfg.output_dir / "logs", cfg.output_dir / "tables", cfg.output_dir / "figures"]
        missing = [path for path in expected_dirs if not path.exists()]
        if missing:
            raise AssertionError(f"Self-test missing directories: {missing}")
        if not list((cfg.output_dir / "figures").glob("*.png")):
            raise AssertionError("Self-test did not produce figures")
        log.info("Self-test passed")


def main(argv: Sequence[str] | None = None) -> int:
    """Program entrypoint. Returns shell-style status code."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config = build_config(args)
    setup_logging(config.verbose)

    log.info("Parsed config:")
    for key, value in asdict(config).items():
        log.info("  %s: %s", key, value)

    try:
        if config.self_test:
            run_self_test()
        else:
            validate_config(config)
            run_workflow(config)
    except Exception as exc:
        log.exception("Workflow failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())