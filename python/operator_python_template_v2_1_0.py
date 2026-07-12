#!/usr/bin/env python3
"""
operator_python_template_v2_1_0.py

Generic Python template for engineering/operator workflows.

Good for:
  - CSV/log analysis
  - plotting and artifact generation
  - hardware runner wrappers
  - repeatable test/report scripts
  - edit-and-learn project scaffolding

Core pattern:
    parse_args -> build_config -> validate_config -> run_workflow

Mental model:
    Config      = typed mission order for this run
    OutputPaths = artifact map for this run
    validate_*  = gates before trust
    process_*   = turn raw input into useful evidence
    save_*      = preserve evidence as files

Operator rule:
    External input is untrusted until path, schema, and type gates pass.

Examples:
    # Run with synthetic data and write outputs under ./output
    python3 operator_python_template_v2_1_0.py

    # Analyze a CSV using specific columns
    python3 operator_python_template_v2_1_0.py --input data.csv --x-column time_s --y-columns command response raw_signal

    # Preview without writing artifacts
    python3 operator_python_template_v2_1_0.py --no-load-run --verbose

    # Run built-in smoke test
    python3 operator_python_template_v2_1_0.py --self-test
"""

from __future__ import annotations

# =============================================================================
# S0. Metadata
# =============================================================================

VERSION = "2.1.0"
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
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

# Non-interactive backend: figures save correctly over SSH/headless terminals.
# This must happen before importing pyplot.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


# =============================================================================
# S2. Constants / defaults
# =============================================================================

DEFAULT_OUTPUT_DIR = Path("output")
VALID_THEMES = ["halcyon-dark", "dark", "light"]


# =============================================================================
# S3. Data models
# =============================================================================

@dataclass(frozen=True)
class Config:
    """Typed run configuration: one immutable mission order."""

    input_path: Path | None
    output_dir: Path
    x_column: str
    y_columns: list[str]
    sample_rate_hz: float
    theme: str
    fig_width: float
    fig_height: float
    dpi: int
    no_plot: bool
    no_load_run: bool
    verbose: bool
    self_test: bool
    run_id: str


@dataclass(frozen=True)
class OutputPaths:
    """Standard artifact directories for one run."""

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

log = logging.getLogger("operator_python_template")


def utc_run_id() -> str:
    """Return a timestamp safe for filenames and artifact IDs."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def setup_logging(verbose: bool) -> None:
    """Configure console logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Keep --verbose focused on this script, not Matplotlib font internals.
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


# =============================================================================
# S5. Path / filesystem helpers
# =============================================================================


def expand_path(path: str | Path | None) -> Path | None:
    """Expand ~ and resolve a path without requiring it to exist."""
    if path is None:
        return None
    return Path(path).expanduser().resolve(strict=False)


def ensure_dir(path: Path, *, no_load_run: bool = False) -> None:
    """Create a directory if needed. Pass directories, not file paths."""
    if no_load_run:
        log.info("[NO-LOAD] mkdir -p %s", path)
        return
    path.mkdir(parents=True, exist_ok=True)


def ensure_output_dirs(paths: OutputPaths, *, no_load_run: bool = False) -> None:
    """Create all standard artifact directories."""
    for path in [paths.root, paths.logs, paths.tables, paths.figures]:
        ensure_dir(path, no_load_run=no_load_run)


def safe_filename(text: str, *, max_len: int = 80) -> str:
    """Turn arbitrary text into a filesystem-safe stem."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text[:max_len] or "artifact"


def backup_if_exists(path: Path, run_id: str, *, no_load_run: bool = False) -> Path | None:
    """Move an existing file out of the way before overwriting."""
    if not path.exists():
        return None

    backup_path = path.with_name(f"{path.name}.bak.{run_id}")
    if no_load_run:
        log.info("[NO-LOAD] backup %s -> %s", path, backup_path)
    else:
        path.replace(backup_path)
        log.info("Backed up %s -> %s", path, backup_path)
    return backup_path


def atomic_write_text(path: Path, text: str, *, no_load_run: bool = False) -> Path:
    """Write text via temp file, then atomic replace."""
    ensure_dir(path.parent, no_load_run=no_load_run)
    if no_load_run:
        log.info("[NO-LOAD] write text %s", path)
        return path

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    log.info("Wrote %s", path)
    return path


def write_json(path: Path, payload: Mapping[str, Any], *, no_load_run: bool = False) -> Path:
    """Write a mapping as pretty JSON."""
    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    return atomic_write_text(path, text, no_load_run=no_load_run)


def write_csv_dicts(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    fieldnames: Sequence[str],
    *,
    no_load_run: bool = False,
) -> Path:
    """Write dictionaries to CSV with explicit field order."""
    ensure_dir(path.parent, no_load_run=no_load_run)
    if no_load_run:
        log.info("[NO-LOAD] write CSV %s", path)
        return path

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    log.info("Wrote %s", path)
    return path


# =============================================================================
# S6. Command helpers
# =============================================================================


def require_command(command: str) -> Path:
    """Require an external executable and return its resolved path."""
    found = shutil.which(command)
    if found is None:
        raise RuntimeError(f"Missing required command: {command}")
    return Path(found)


def run_command(
    cmd: Sequence[str],
    *,
    no_load_run: bool = False,
    check: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """
    Run a command safely without shell=True.

    Rule:
        Pass command and args as a list, not one shell string.
        Good: run_command(["python3", "script.py", "--flag"])
        Avoid: run_command(["python3 script.py --flag"])
    """
    if no_load_run:
        log.info("[NO-LOAD] %s", " ".join(cmd))
        return None

    log.debug("RUN: %s", " ".join(cmd))
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        capture_output=True,
    )


# =============================================================================
# S7. DataFrame / table helpers
# =============================================================================


def normalize_columns(columns: str | Sequence[str]) -> list[str]:
    """
    Accept one column name or many.

    Why this exists:
        Strings are iterable in Python. list("time_s") becomes characters.
        This function prevents that bug and catches list-inside-list mistakes.
    """
    if isinstance(columns, str):
        return [columns]

    normalized = list(columns)
    for col in normalized:
        if not isinstance(col, str):
            raise TypeError(
                f"Column names must be strings. Got {col!r} ({type(col).__name__}). "
                "Did you accidentally pass a list inside a list?"
            )
    return normalized


def unique_preserve_order(items: Sequence[str]) -> list[str]:
    """Remove duplicates while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def require_columns(df: pd.DataFrame, columns: str | Sequence[str]) -> None:
    """Fail fast if a DataFrame is missing expected columns."""
    required = normalize_columns(columns)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Available: {list(df.columns)}")


def coerce_numeric_columns(df: pd.DataFrame, columns: str | Sequence[str]) -> pd.DataFrame:
    """Convert selected columns to numeric and fail if conversion creates NaN."""
    cols = normalize_columns(columns)
    require_columns(df, cols)
    out = df.copy()
    for col in cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    bad_mask = out[cols].isna().any(axis=1)
    if bad_mask.any():
        bad_rows = out.loc[bad_mask, cols].head(10)
        raise ValueError(f"Non-numeric values after conversion. First bad rows:\n{bad_rows}")
    return out


def data_quality_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Return compact evidence about table shape, dtypes, and missingness."""
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_by_column": {col: int(df[col].isna().sum()) for col in df.columns},
    }


def numeric_stats(df: pd.DataFrame, columns: str | Sequence[str]) -> dict[str, dict[str, float]]:
    """Return min/max/mean/std for numeric columns."""
    stats: dict[str, dict[str, float]] = {}
    for col in normalize_columns(columns):
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        stats[col] = {
            "min": float(df[col].min()),
            "max": float(df[col].max()),
            "mean": float(df[col].mean()),
            "std": float(df[col].std()),
        }
    return stats


def add_derivative_column(df: pd.DataFrame, *, x: str, y: str, output_col: str | None = None) -> pd.DataFrame:
    """
    Add dy/dx using finite differences.

    Useful for:
        velocity from position, heating rate from temperature, trend rate from health score.
    """
    require_columns(df, [x, y])
    out = df.copy()
    output_col = output_col or f"d_{y}_d_{x}"
    dx = out[x].diff()
    dy = out[y].diff()
    out[output_col] = dy / dx.replace(0, math.nan)
    return out


def add_rolling_mean(df: pd.DataFrame, *, column: str, window: int, output_col: str | None = None) -> pd.DataFrame:
    """Add a rolling mean while keeping the original signal unchanged."""
    if window <= 0:
        raise ValueError("window must be positive")
    require_columns(df, [column])
    out = df.copy()
    output_col = output_col or f"{column}_rolling_mean_{window}"
    out[output_col] = out[column].rolling(window=window, min_periods=1).mean()
    return out


def load_or_make_dataframe(config: Config) -> pd.DataFrame:
    """Load CSV if provided; otherwise create a small synthetic dataset."""
    if config.input_path is None:
        log.warning("No --input provided. Creating synthetic placeholder data.")
        return make_synthetic_dataset(sample_rate_hz=config.sample_rate_hz)

    if not config.input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {config.input_path}")
    if config.input_path.is_dir():
        raise ValueError(f"Input path is a directory, expected CSV file: {config.input_path}")
    if config.input_path.suffix.lower() != ".csv":
        raise ValueError(f"Expected .csv input, got {config.input_path.suffix!r}")

    df = pd.read_csv(config.input_path)
    log.info("Loaded %s shape=%s", config.input_path, df.shape)
    return df


def make_synthetic_dataset(*, sample_rate_hz: float = 10.0, seconds: float = 20.0) -> pd.DataFrame:
    """Create deterministic synthetic signal data so the template runs immediately."""
    n = max(2, int(sample_rate_hz * seconds))
    time_s = pd.Series([i / sample_rate_hz for i in range(n)], name="time_s")
    command = pd.Series([1.0 if t >= 2.0 else 0.0 for t in time_s], name="command")
    response = pd.Series([1.0 - math.exp(-max(t - 2.0, 0.0) / 4.0) for t in time_s], name="response")
    raw_signal = response + 0.03 * pd.Series([math.sin(2.0 * math.pi * 0.7 * t) for t in time_s])
    return pd.DataFrame({"time_s": time_s, "command": command, "response": response, "raw_signal": raw_signal})


# =============================================================================
# S8. Plotting helpers
# =============================================================================


def apply_plot_theme(fig: plt.Figure, ax: plt.Axes, theme: str) -> None:
    """Apply a small, readable plot theme."""
    if theme == "light":
        ax.grid(True, alpha=0.3)
        return

    if theme == "halcyon-dark":
        bg = "#07090D"       # soot-black
        panel = "#282829"    # cockpit-panel
        text = "#F2E8D5"     # warm bone
        spine = "#B88746"    # aged brass
        grid = "#FFBF00"     # reactor amber grid
        colors = [
            "#B7410E", # ember rust
            "#C97C5D", # copper rose
            "#8FA37A", # moss green
            "#76B7B2",	# signal blue
            "#A77BD4"  # low violet
            ]

    else:
        bg = "#0B0D10"
        panel = "#141820"
        text = "#E8E8E8"
        spine = "#A0A0A0"
        grid = "#5A5A5A"
        colors = [
            "#B7410E",
            "#8FA37A",
            "#E6C978",
            "#4FA3B8"
            ]

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


def save_line_plot(
    df: pd.DataFrame,
    *,
    x: str,
    y_columns: str | Sequence[str],
    output_path: Path,
    title: str,
    theme: str,
    fig_size: tuple[float, float],
    dpi: int,
    no_load_run: bool = False,
) -> Path:
    """Save a multi-signal line plot."""
    y_cols = normalize_columns(y_columns)
    require_columns(df, [x, *y_cols])
    ensure_dir(output_path.parent, no_load_run=no_load_run)

    if no_load_run:
        log.info("[NO-LOAD] save figure %s", output_path)
        return output_path

    fig, ax = plt.subplots(figsize=fig_size)
    apply_plot_theme(fig, ax, theme)

    for col in y_cols:
        ax.plot(df[x], df[col], label=col, linewidth=1.8)

    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(", ".join(y_cols))
    ax.legend()
    apply_plot_theme(fig, ax, theme)  # Re-apply after legend exists.
    fig.tight_layout()
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
# S9. Workflow hooks
# =============================================================================


def columns_needed(config: Config) -> list[str]:
    """Centralize required columns for this workflow."""
    return unique_preserve_order([config.x_column, *config.y_columns])


def process_data(config: Config) -> pd.DataFrame:
    """Load, validate, coerce, and enrich input data."""
    df = load_or_make_dataframe(config)
    needed = columns_needed(config)
    require_columns(df, needed)
    df = coerce_numeric_columns(df, needed)

    # Example enrichment: add a smoothed version and derivative of the first y signal.
    first_y = config.y_columns[0]
    df = add_rolling_mean(df, column=first_y, window=5)
    df = add_derivative_column(df, x=config.x_column, y=first_y)
    return df


def save_dataframe_csv(df: pd.DataFrame, path: Path, *, no_load_run: bool = False) -> Path:
    """Write a DataFrame to CSV with consistent no-load behavior."""
    ensure_dir(path.parent, no_load_run=no_load_run)
    if no_load_run:
        log.info("[NO-LOAD] write DataFrame CSV %s shape=%s", path, df.shape)
        return path
    df.to_csv(path, index=False)
    log.info("Wrote %s shape=%s", path, df.shape)
    return path


def write_manifest(config: Config, paths: OutputPaths) -> Path:
    """Write run metadata before processing."""
    payload = {
        **asdict(config),
        "input_path": str(config.input_path) if config.input_path else None,
        "output_dir": str(config.output_dir),
        "python": sys.version,
        "script_version": VERSION,
        "author": AUTHOR,
        "cwd": str(Path.cwd()),
    }
    return write_json(paths.logs / f"run_manifest_{config.run_id}.json", payload, no_load_run=config.no_load_run)


def run_workflow(config: Config) -> dict[str, Any]:
    """Readable top-level operator flow."""
    log.info("Starting workflow run_id=%s", config.run_id)
    paths = OutputPaths.from_config(config)
    ensure_output_dirs(paths, no_load_run=config.no_load_run)
    write_manifest(config, paths)

    df = process_data(config)
    artifacts: list[str] = []

    processed_path = paths.tables / f"processed_{config.run_id}.csv"
    artifacts.append(str(save_dataframe_csv(df, processed_path, no_load_run=config.no_load_run)))

    if not config.no_plot:
        fig_path = paths.figures / f"{config.run_id}_primary_signal.png"
        artifacts.append(
            str(
                save_line_plot(
                    df,
                    x=config.x_column,
                    y_columns=config.y_columns,
                    output_path=fig_path,
                    title="Primary Signal",
                    theme=config.theme,
                    fig_size=(config.fig_width, config.fig_height),
                    dpi=config.dpi,
                    no_load_run=config.no_load_run,
                )
            )
        )

    summary = {
        "status": "ok",
        "run_id": config.run_id,
        "data_quality": data_quality_summary(df),
        "numeric_stats": numeric_stats(df, columns_needed(config)),
        "artifacts": artifacts,
    }
    write_json(paths.logs / f"summary_{config.run_id}.json", summary, no_load_run=config.no_load_run)
    log.info("Workflow complete")
    return summary


# =============================================================================
# S10. CLI / configuration
# =============================================================================


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse raw command-line arguments."""
    parser = argparse.ArgumentParser(description="Operator Python template v2.1.0")
    parser.add_argument("--input", "-i", type=Path, default=None, help="Optional input CSV file.")
    parser.add_argument("--output-dir", "-o", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--x-column", default="time_s", help="X-axis/time column.")
    parser.add_argument("--y-columns", "-y", nargs="+", default=["raw_signal"], help="One or more y/signal columns.")
    parser.add_argument("--sample-rate-hz", type=float, default=10.0, help="Nominal sample rate for generated data.")
    parser.add_argument("--theme", choices=VALID_THEMES, default="halcyon-dark", help="Plot theme.")
    parser.add_argument("--fig-width", type=float, default=10.0, help="Figure width in inches.")
    parser.add_argument("--fig-height", type=float, default=5.0, help="Figure height in inches.")
    parser.add_argument("--dpi", type=int, default=160, help="Saved figure DPI.")
    parser.add_argument("--no-plot", action="store_true", help="Skip figure generation.")
    parser.add_argument("--no-load-run", action="store_true", help="Preview actions without writing artifacts.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run a smoke test in a temporary directory.")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    """Convert argparse namespace into typed Config."""
    return Config(
        input_path=expand_path(args.input),
        output_dir=expand_path(args.output_dir) or DEFAULT_OUTPUT_DIR.resolve(strict=False),
        x_column=args.x_column,
        y_columns=normalize_columns(args.y_columns),
        sample_rate_hz=args.sample_rate_hz,
        theme=args.theme,
        fig_width=args.fig_width,
        fig_height=args.fig_height,
        dpi=args.dpi,
        no_plot=args.no_plot,
        no_load_run=args.no_load_run,
        verbose=args.verbose,
        self_test=args.self_test,
        run_id=utc_run_id(),
    )


def validate_config(config: Config) -> None:
    """Validate config before doing side effects."""
    if config.sample_rate_hz <= 0:
        raise ValueError("--sample-rate-hz must be positive")
    if config.fig_width <= 0 or config.fig_height <= 0:
        raise ValueError("figure dimensions must be positive")
    if config.dpi <= 0:
        raise ValueError("--dpi must be positive")
    if config.theme not in VALID_THEMES:
        raise ValueError(f"Unsupported theme: {config.theme}")
    if config.input_path is not None and not config.input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {config.input_path}")


# =============================================================================
# S11. Self-test / V&V hook
# =============================================================================


def run_self_test() -> None:
    """Run a small workflow smoke test in an isolated temporary directory."""
    with tempfile.TemporaryDirectory(prefix="operator_py_template_") as tmp_dir:
        cfg = Config(
            input_path=None,
            output_dir=Path(tmp_dir) / "output",
            x_column="time_s",
            y_columns=["raw_signal"],
            sample_rate_hz=10.0,
            theme="halcyon-dark",
            fig_width=8.0,
            fig_height=4.0,
            dpi=120,
            no_plot=False,
            no_load_run=False,
            verbose=True,
            self_test=True,
            run_id="SELF_TEST",
        )
        validate_config(cfg)
        summary = run_workflow(cfg)
        if summary["status"] != "ok":
            raise AssertionError(f"Self-test status was not ok: {summary}")
        expected = [Path(p) for p in summary["artifacts"]]
        missing = [p for p in expected if not p.exists()]
        if missing:
            raise AssertionError(f"Self-test missing artifacts: {missing}")
        log.info("Self-test passed")


# =============================================================================
# S12. Syntax crib / copy-paste snippets
# =============================================================================

"""
Python syntax crib
------------------

# Path handling
path = Path("~/Vec/data/example.csv").expanduser()
folder = path.parent
stem = path.stem          # filename without suffix
suffix = path.suffix      # ".csv"

# Lists vs strings
cols = normalize_columns("raw_signal")                 # ["raw_signal"]
cols = normalize_columns(["command", "response"])      # ["command", "response"]

# DataFrame basics
df.head(5)                    # first 5 rows
df.iloc[0]                    # first row by position
df.loc[df["temp_c"] > 60]     # rows matching condition
df["temp_c"].to_list()        # all values from a column
for row in df.itertuples(index=False):
    print(row.time_s, row.raw_signal)

# Dict iteration
for key, value in payload.items():
    print(key, value)

# Safe command execution
run_command(["python3", "script.py", "--input", str(path)])
"""


# =============================================================================
# S13. Entrypoint
# =============================================================================


def main(argv: Sequence[str] | None = None) -> int:
    """Program entrypoint. Return shell-style status code."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config = build_config(args)
    setup_logging(config.verbose or config.self_test)

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
