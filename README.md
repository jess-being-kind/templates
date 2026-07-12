# Operator Templates

Reusable Bash, Python, and MATLAB starting points for engineering automation, data analysis, test workflows, and evidence-backed debugging.

These templates reduce setup friction without hiding the important parts. Each provides structured control flow, explicit configuration, input validation, logging, artifact handling, and a clear place to insert project-specific logic.

> **Operating principle:** Treat external input as untrusted until it passes path, schema, and type checks.

## Templates

| Template | Version | Best for | Core workflow |
|---|---:|---|---|
| [`operator_bash_template`](./operator_bash_template) | 3.1.0 | Automation, environment setup, file operations, and hardware/tool wrappers | `parse_args → validate_config → run_workflow` |
| [`operator_python_template.py`](./operator_python_template.py) | 3.0.0 | CSV/log analysis, plotting, report artifacts, and repeatable test scripts | `parse_args → build_config → validate_config → run_workflow` |
| [`operator_matlab_template.m`](./operator_matlab_template.m) | 3.0.0 | Sensor analysis, thermal characterization, fleet metrics, and repeatability studies | `CONFIG → LOAD → VALIDATE → PROCESS → PLOT → EXPORT` |

## Design goals

- **Readable first:** Sectioned layouts, descriptive names, and explicit control flow.
- **Safe by default:** Dry-run or no-load modes before side effects.
- **Evidence preserving:** Timestamped manifests, summaries, tables, and figures.
- **Validation before trust:** Paths, required columns, types, dimensions, and configuration are checked before processing.
- **Reusable without being opaque:** Helpers are included, but the main workflow remains easy to follow and modify.
- **Operator-friendly:** Useful logging, deterministic output locations, self-tests, and practical syntax references.

## Quick start

Clone the repository:

```bash
git clone https://github.com/jess-being-kind/templates.git
cd templates
```

## Bash

The Bash template defaults to dry-run behavior. Use `--apply` only when you are ready to permit filesystem changes.

```bash
chmod +x operator_bash_template

./operator_bash_template --help
./operator_bash_template --self-test
./operator_bash_template --input ./example.csv --verbose
./operator_bash_template --input ./example.csv --apply
```

Useful flags:

```text
--input PATH
--output-dir PATH
--apply
--dry-run
--no-load-run
--force
--verbose
--self-test
--version
```

### Safety model

Potential side effects pass through shared execution and file-writing helpers.

By default:

```text
APPLY=0
```

Commands and writes are previewed rather than executed. Passing `--apply` changes this behavior.

## Python

Install the current runtime dependencies:

```bash
python3 -m pip install pandas matplotlib
```

Run the built-in synthetic-data workflow:

```bash
python3 operator_python_template.py
```

Analyze a CSV:

```bash
python3 operator_python_template.py \
  --input data.csv \
  --x-column time_s \
  --y-columns command response raw_signal
```

Preview actions without writing artifacts:

```bash
python3 operator_python_template.py --no-load-run --verbose
```

Run the smoke test:

```bash
python3 operator_python_template.py --self-test
```

The Python template currently provides:

- typed, immutable configuration using `dataclasses`
- `pathlib.Path`-based path handling
- CSV loading and deterministic synthetic data
- DataFrame schema and numeric-type validation
- rolling means and finite-difference derivatives
- JSON manifests and summaries
- processed CSV export
- headless Matplotlib rendering
- `halcyon-dark`, `dark`, and `light` plot themes
- atomic text writes and backup helpers
- safe subprocess execution without `shell=True`
- an isolated self-test that verifies generated artifacts

## MATLAB

Open the file in MATLAB and press **Run**, or execute:

```matlab
run("operator_matlab_template.m")
```

Before using it for a project, update the configuration block near the top of the script:

```matlab
cfg.rootDir
cfg.inputFile
cfg.outputDir
cfg.timeColumn
cfg.signalColumns
```

The MATLAB template keeps source data immutable and writes derived tables, figures, logs, configuration records, and summaries into output folders.

It is intended for workflows such as:

- thermal characterization
- sensor-data analysis
- fleet reliability metrics
- repeatability studies
- quick report-artifact generation

## Recommended workflow

1. Copy the closest template into the project.
2. Rename it for the actual mission.
3. Update metadata, default paths, and CLI or configuration fields.
4. Replace the marked workflow section first.
5. Run the dry-run, no-load, or self-test path.
6. Test with a small, known dataset.
7. Inspect generated manifests, summaries, tables, and figures.
8. Commit the project-specific version once its behavior is understood.

Example:

```bash
cp operator_python_template.py \
  ~/Vec/Engineering/my_project/analyze_test.py
```

## Verification and validation

Before trusting a modified template, verify both its implementation and its outputs.

### Bash

Check syntax:

```bash
bash -n operator_bash_template
```

Run the built-in self-test:

```bash
./operator_bash_template --self-test
```

Optional static analysis:

```bash
shellcheck operator_bash_template
```

Confirm that:

- dry-run mode does not alter the filesystem
- `--apply` performs only the intended actions
- existing files are skipped or backed up as expected
- invalid paths fail with clear messages
- manifests and summaries are written to the expected location

### Python

Compile without executing:

```bash
python3 -m py_compile operator_python_template.py
```

Run the built-in self-test:

```bash
python3 operator_python_template.py --self-test
```

Optional linting and type checks:

```bash
ruff check operator_python_template.py
mypy operator_python_template.py
```

Confirm that:

- missing columns fail before processing
- nonnumeric signal values fail clearly
- no-load mode does not write artifacts
- processed tables preserve the original raw columns
- generated statistics match a known test dataset
- figure axes, labels, units, and selected signals are correct
- manifests accurately describe the run configuration

### MATLAB

Run the script against a small, known-good dataset and confirm that:

- expected columns are accepted
- malformed or missing inputs fail clearly
- raw source data remains unchanged
- generated tables contain expected values
- plots use the intended signals and units
- output paths and run identifiers are correct
- summaries agree with independently calculated values

MATLAB Code Analyzer can also identify syntax, compatibility, and maintainability issues before deployment.

## Repository layout

```text
templates/
├── operator_bash_template
├── operator_python_template.py
└── operator_matlab_template.m
```

## Customization notes

The defaults reflect a personal engineering workspace and may include paths under:

```text
~/Vec/Engineering/
```

Change those defaults when copying a template into another environment. Prefer environment variables and command-line arguments over repeatedly editing hard-coded paths.

These templates are intentionally substantial. They are meant to serve as references, scaffolds, and teaching tools rather than minimal “hello world” examples.

## Status

These are evolving working templates. Interfaces, defaults, and helper functions may change between versions, so check the version metadata before copying updates into an existing project.

## Author

**V Halcyon**

*Observe directly. Validate physically. Debug iteratively.*
