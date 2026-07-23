# tracehold

> Turn ambiguous field failures into structured, timestamped, integrity-conscious engineering case files.

`tracehold` is a Bash-based incident capture and initial-triage tool for engineering problems where hardware, software, communications, configuration, environment, operator procedure, and telemetry may all be interacting.

It creates a consistent case structure for preserving evidence, recording the original symptom, separating raw material from derived analysis, and handing an investigation to another engineer without relying on verbal-only context.

```text
Hold the evidence.
Keep the context.
Find the truth.
```

**Operator principle:** Observe directly. Validate physically. Debug iteratively.

## Project status

**Version:** `1.1.0`  
**Maturity:** early alpha

The `new` workflow is the current center of gravity. The remaining commands are experimental or scaffolded and should not yet be treated as production incident-management tooling.

| Command | Intended purpose | v1.1.0 state |
|---|---|---|
| `new` | Create a case and initial triage structure | Implemented primary workflow |
| `add` | Copy evidence into an existing case | Experimental; multi-file ingest, dry-run routing, collision backup, and initial SHA-256 capture implemented |
| `collect` | Run a collection profile | Scaffold only |
| `verify` | Validate case structure and evidence integrity | Scaffold only |
| `bundle` | Create a portable case archive | Scaffold only |

Interfaces, file layouts, and option names may change before the first stable release.

## Why tracehold exists

Field failures rarely arrive as clean engineering problems.

They arrive as:

- “The vehicle acted strange.”
- “The link dropped for a few seconds.”
- “This only happens at one site.”
- “It worked before the update.”
- “The logs do not agree with what the operator saw.”
- “We restarted it and the problem disappeared.”

The first challenge is often not solving the failure. It is preserving enough reliable context to determine what actually happened.

`tracehold` is designed to establish:

- what was directly observed;
- what remains unknown;
- which assumptions require validation;
- which assets, sites, versions, and time windows are involved;
- where original evidence is stored;
- which artifacts are derived from that evidence;
- what containment has already occurred;
- who owns the next action;
- and what evidence would discriminate between competing hypotheses.

## Design principles

### Dry-run by default

The script defaults to preview mode. File-writing helpers and commands routed through `run_cmd()` perform work only when `--apply` is supplied.

```bash
./tracehold.sh new \
    --title intermittent_link_loss \
    --description "Vehicle loses command link during climb" \
    --severity P1 \
    --asset AV-042
```

Apply the planned changes only after reviewing the preview:

```bash
./tracehold.sh new \
    --title intermittent_link_loss \
    --description "Vehicle loses command link during climb" \
    --severity P1 \
    --asset AV-042 \
    --apply
```

The current `add` copy path is routed through `run_cmd()`, so dry-run previews do not perform the evidence copy or checksum-manifest append. `add` remains experimental because destination-hash verification and structured provenance are not complete.

### Preserve raw evidence

Original evidence should remain distinguishable from:

- cleaned data;
- extracts;
- generated timelines;
- figures;
- summaries;
- transformed logs;
- and other analytical output.

The generated layout separates `evidence/` from `derived/` for this reason.

### Preserve execution context

Each process receives a UTC run ID and constructs a JSON-formatted run manifest containing:

- script and Tracehold version metadata;
- script path and working directory;
- run ID and generation timestamp;
- process identifiers;
- selected command flags;
- apply, force, verbose, and self-test state;
- resolved input values;
- and whether each input was explicitly supplied.

The run manifest currently uses a `.txt` extension even though its content is JSON.

### Make handoff possible

A case should contain enough structured context for another engineer to continue the investigation without a lengthy verbal reconstruction.

### Treat hypotheses as hypotheses

The initial-triage report separates:

- reported behavior;
- known facts;
- unknowns;
- assumptions requiring validation;
- working hypotheses;
- supporting and contradicting evidence;
- and planned discriminating tests.

### Fail explicitly

Fatal validation and runtime conditions are routed through `hardstop()`, which emits a clear error and exits with a deliberate nonzero status.

## Requirements

### Required for current workflows

- Linux or a GNU-compatible environment
- Bash `4.3` or newer
- `jq`
- `realpath`
- `sha256sum`
- standard utilities including `date`, `mkdir`, `cp`, `mv`, `rm`, and `mktemp`

Bash `4.3+` is required because the CLI helpers use nameref variables through `local -n`.

`jq` is currently required for every normal workflow, including dry-run, because the run manifest is constructed before it is handed to the file-writing layer.

### Defined but currently disabled collectors

The source contains environment, software, and checksum helper functions, but the `new` workflow does not currently invoke them. If enabled later, they may use utilities such as:

- `uname`
- `uptime`
- `free`
- `df`
- `lsusb`
- `lspci`
- `dmesg`

Some of those commands may require additional packages or permissions.

## Installation

### 1. Clone and inspect the project

```bash
git clone <repository-url>
cd tracehold
```

Make the script executable and verify its syntax:

```bash
chmod +x tracehold.sh
bash -n tracehold.sh
./tracehold.sh --version
./tracehold.sh --help
```

### 2. Install the command

A user-local installation does not require root privileges:

```bash
mkdir -p "$HOME/.local/bin"
install -m 0755 tracehold.sh "$HOME/.local/bin/tracehold"
```

Make sure the directory is in `PATH`:

```bash
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
```

To make that `PATH` update persistent, place the same block in `~/.bashrc`, then reload it:

```bash
source "$HOME/.bashrc"
```

Verify the installed command:

```bash
command -v tracehold
tracehold --version
tracehold --help
```

#### Development symlink alternative

During active development, a symlink keeps the installed command pointed at the working tree:

```bash
mkdir -p "$HOME/.local/bin"
ln -sfn "$(pwd)/tracehold.sh" "$HOME/.local/bin/tracehold"
```

Use either the copied installation or the development symlink—not both at different locations in `PATH`.

### 3. Install Bash completion

Tracehold generates its completion script from the same command schema used by parsing, validation, and generated help:

```bash
mkdir -p "$HOME/.local/share/bash-completion/completions"
tracehold --completion bash \
    > "$HOME/.local/share/bash-completion/completions/tracehold"
```

Validate and load it in the current shell:

```bash
bash -n "$HOME/.local/share/bash-completion/completions/tracehold"
source "$HOME/.local/share/bash-completion/completions/tracehold"
```

Then test the guided sequence:

```text
tracehold new <TAB>
# → --title

tracehold add <TAB>
# → --case
```

Most systems with the `bash-completion` package load files from the user completion directory automatically in new shells. If yours does not, add this guarded fallback to `~/.bashrc`:

```bash
completion_file="$HOME/.local/share/bash-completion/completions/tracehold"

[[ -r "$completion_file" ]] &&
    source "$completion_file"
```

After changing Tracehold's command schema, regenerate the installed completion file:

```bash
tracehold --completion bash \
    > "$HOME/.local/share/bash-completion/completions/tracehold"
```

### 4. Optional uninstall

Remove the installed command and generated completion file:

```bash
rm -f "$HOME/.local/bin/tracehold"
rm -f "$HOME/.local/share/bash-completion/completions/tracehold"
```

## Bash completion

Bash programmable completion is implemented as a thin generated adapter over Tracehold's internal schema. The completion file does not maintain a second independent list of commands or options. Instead, it asks the executable for context-aware candidates through an internal completion interface.

The shared schema defines:

- command names and descriptions;
- required options for each command;
- allowed optional and execution options;
- scalar, variadic, enum, case-ID, file, directory, and flag value types;
- enum values for severity, evidence type, and collection profile;
- canonical CLI spellings and supported aliases.

That schema is consumed by:

```text
argument parsing
    ↕
required/allowed validation
    ↕
generated command-contract help
    ↕
Bash programmable completion
```

### Guided required inputs

Completion advances through the first missing required input:

```text
tracehold new <TAB>
→ --title

tracehold new --title link_loss <TAB>
→ --description

tracehold new --title link_loss --description "Link dropped" <TAB>
→ --severity

tracehold new --title link_loss --description "Link dropped" --severity P1 <TAB>
→ --asset
```

After the required contract is satisfied, completion offers the remaining options that are legal for the selected command.

### Context-aware values

Completion provides:

- `P0` through `P4` after `--severity`;
- `raw`, `photo`, `log`, and `note` after `--type`;
- `default`, `general`, and `environment` after `--profile`;
- existing case IDs after `--case`;
- filesystem paths after `--file`;
- directories after `--output-dir`.

Case-ID completion respects an earlier `--output-dir` in the same command:

```bash
tracehold add \
    --output-dir /tmp/tracehold-cases \
    --case <TAB>
```

### Variadic-option behavior

After one value is present, completion treats a variadic required option as satisfied and advances to the next missing requirement:

```text
tracehold add --case TH_... --file vehicle.log <TAB>
→ --type
```

Additional values can still be entered manually before requesting the next option:

```bash
tracehold add \
    --case TH_... \
    --file vehicle.log ground.log radio.log \
    --type log
```

### Completion architecture

The public interface is:

```bash
tracehold --completion bash
```

The generated adapter uses an internal `__complete` protocol. `__complete` is an implementation detail for shell integration and is not part of the stable operator-facing CLI.

## Quick start

Preview a case without changing the filesystem:

```bash
./tracehold.sh new \
    --title gps_quality_degradation \
    --description "Position estimate becomes unstable near Site 04" \
    --severity P2 \
    --asset AV-017
```

Create a more fully described case:

```bash
./tracehold.sh new \
    --title gps_quality_degradation \
    --description "Position estimate becomes unstable near Site 04" \
    --severity P2 \
    --asset AV-017 AV-023 \
    --site SITE-04 \
    --reported-by "Flight Operations" \
    --owner "V Halcyon" "Navigation Engineering" \
    --first-observed "2026-07-18T04:12:00Z" \
    --last-observed "2026-07-18T04:37:00Z" \
    --operational-impact "Mission aborted and assets temporarily grounded" \
    --affected-scope "Two assets at one site; fleet scope unknown" \
    --recent-change "Navigation firmware updated" "Site antenna replaced" \
    --containment-status "Affected assets grounded pending review" \
    --triage-confidence low \
    --profile general \
    --apply
```

Run with diagnostic output:

```bash
./tracehold.sh new \
    --title gps_quality_degradation \
    --description "Position estimate becomes unstable near Site 04" \
    --severity P2 \
    --asset AV-017 \
    --apply \
    --verbose
```

## Command model

```text
tracehold COMMAND [OPTIONS]
```

Exactly one primary command is required for normal operation.

```text
new       Create a new investigation case
add       Copy one evidence file into an existing case
collect   Select a case for a future collection workflow
verify    Select a case for a future verification workflow
bundle    Select a case for a future archive workflow
```

`--help`, `--version`, `--self-test`, and `--completion bash` do not require a primary command.

## Creating a case

```bash
./tracehold.sh new [options]
```

A generated case ID follows this pattern:

```text
TH_<YYYYMMDD_HHMMSS_UTC>_<title>
```

Example:

```text
TH_20260718_041200_UTC_intermittent_link_loss
```

The title is appended directly to the directory name. v1.1.0 does not sanitize it, so use a filesystem-safe slug containing letters, numbers, underscores, or hyphens.

### Required fields

| Option | Description |
|---|---|
| `--title SLUG` | Short investigation title appended to the case ID |
| `--description STRING` | Initial observed symptom or problem description |
| `--severity P0..P4` | Initial priority classification |
| `--asset ID [ID ...]` | One or more affected assets, vehicles, devices, or systems |

Severity is validated against `P0`, `P1`, `P2`, `P3`, and `P4`.

### Ownership and time

| Option | Description |
|---|---|
| `--reported-by STRING` | Person, team, customer, operator, or system reporting the issue |
| `--owner STRING [STRING ...]` | One or more current investigation owners |
| `--first-observed STRING` | Earliest known observation time |
| `--last-observed STRING` | Most recent known observation time |

Use UTC ISO 8601 timestamps where possible:

```bash
--first-observed "2026-07-18T04:12:00Z"
```

Timestamp format is not currently validated.

### Scope and triage state

| Option | Description |
|---|---|
| `--site ID [ID ...]` | One or more affected sites or operating locations |
| `--operational-impact STRING` | Actual operational consequence or credible risk |
| `--affected-scope STRING` | Known affected fleet, asset, site, version, or population |
| `--recent-change STRING [STRING ...]` | One or more relevant recent changes |
| `--status STRING` | Current investigation or operational state |
| `--repro-status STRING` | Current reproduction state |
| `--containment-status STRING` | Current containment action or restriction |
| `--triage-confidence STRING` | Confidence in the current assessment |
| `--profile NAME` | Collection or analysis profile label |

`--repro-status`, `--triage-confidence`, and `--profile` are currently recorded as supplied and are not enum-validated.

Conventional reproduction values include:

```text
not-attempted
not-reproduced
intermittent
reproduced
```

Conventional confidence values include:

```text
low
medium
high
```

### Variadic options

The following options accept one or more values in a single occurrence:

- `--asset`
- `--site`
- `--owner`
- `--recent-change`

They consume every following argument until the next token beginning with `-`.

```bash
--asset AV-017 AV-023 AV-041 \
--site SITE-04 SITE-09 \
--owner "V Halcyon" "RF Engineering" \
--recent-change "Firmware updated" "Antenna replaced"
```

Quote each multi-word value so it remains one array element.

## Adding evidence

```bash
./tracehold.sh add \
    --case CASE_ID \
    --file PATH [PATH ...] \
    --type TYPE \
    --apply
```

Accepted evidence types and destinations:

| Type | Destination |
|---|---|
| `raw` | `evidence/raw/` |
| `photo` | `evidence/photos/` |
| `log` | `evidence/logs/` |
| `note` | `evidence/operator_notes/` |

Example:

```bash
./tracehold.sh add \
    --case TH_20260718_041200_UTC_intermittent_link_loss \
    --file ./vehicle.log \
    --type log \
    --apply
```

The input file must exist and be a regular file.

> [!CAUTION]
> `add` remains experimental in v1.1.0. It discovers prior case manifests, routes copy and checksum-record operations through the dry-run boundary, requires `--force` for same-named destinations, and captures an initial source SHA-256. It does not yet compare the preserved destination hash, perform an atomic copy transaction, or write full structured provenance. Do not treat the current checksum line as complete chain-of-custody evidence.

## Collecting evidence

```bash
./tracehold.sh collect \
    --case CASE_ID \
    --profile PROFILE \
    --apply
```

The default profile is `default` when `--profile` is omitted.

Planned profile names currently described by the CLI include:

```text
default
general
bash
python
git
```

Profile names are not validated, and profile execution is not implemented. The current command only selects the case, records run metadata when applied, and emits debug output when verbose mode is enabled.

## Verifying a case

```bash
./tracehold.sh verify \
    --case CASE_ID \
    --apply
```

The intended workflow is to validate:

- required directories and artifacts;
- missing or unexpected files;
- checksum availability;
- evidence integrity;
- and consistency between case metadata and stored files.

Those checks are not implemented in v1.1.0. Do not interpret a successful `verify` exit as evidence that a case is complete or intact.

## Bundling a case

```bash
./tracehold.sh bundle \
    --case CASE_ID \
    --apply
```

The intended workflow is to create a portable `.tar.gz` archive for handoff, escalation, storage, review, or controlled transfer.

Archive creation is not implemented in v1.1.0.

## Execution options

| Option | Behavior |
|---|---|
| `--apply` | Perform file writes and commands routed through the controlled helpers |
| `--dry-run` | Preview routed operations without changing the filesystem; default mode |
| `--no-load-run` | Legacy alias for `--dry-run` |
| `--force` | Replace `write_file()`-managed artifacts after timestamped backup |
| `-v`, `--verbose` | Enable diagnostic logging |
| `--self-test` | Run the built-in temporary-directory smoke test |
| `--completion bash` | Print the Bash completion adapter generated from the shared command schema |
| `--version` | Print the current version |
| `-h`, `--help` | Display CLI help |

`--force` applies to artifacts managed by `write_file()`. It does not currently protect the direct evidence copy in `add`.

## Path and configuration model

At startup, v1.1.0 resolves defaults approximately as follows:

```bash
ROOT="${ROOT:-${HOME}/Vec}"
ENGINEERING_DIR="${ENGINEERING_DIR:-${ROOT}/Engineering}"
OUTPUT_DIR="${OUTPUT_DIR:-${ENGINEERING_DIR}/projects/active/tracehold/cases}"
```

The final default assumes the script is named `tracehold.sh`; internally, the directory component is derived from the script filename without `.sh`.

### `ROOT`

Base workspace path:

```bash
export ROOT="$HOME/Vec"
```

### `ENGINEERING_DIR`

Engineering workspace root:

```bash
export ENGINEERING_DIR="$ROOT/Engineering"
```

### `OUTPUT_DIR`

Default case-storage root:

```bash
export OUTPUT_DIR="$HOME/tracehold-data"
```

A per-run override takes precedence:

```bash
./tracehold.sh new \
    --output-dir "$HOME/tracehold-data" \
    --title link_loss \
    --description "Command link dropped during climb" \
    --severity P1 \
    --asset AV-042
```

### `NO_COLOR`

Disable ANSI color output:

```bash
export NO_COLOR=1
```

## Generated case structure

A successful applied `new` workflow currently produces a structure similar to:

```text
cases/
├── logs/
├── artifacts/
└── TH_<run-id>_<title>/
    ├── manifest/
    │   ├── run_manifest_<run-id>.txt
    │   ├── case_manifest_<run-id>.txt
    │   └── summary_<run-id>.txt
    ├── evidence/
    │   ├── raw/
    │   ├── photos/
    │   ├── logs/
    │   └── operator_notes/
    ├── derived/
    │   ├── timelines/
    │   ├── extracts/
    │   └── figures/
    ├── commands/
    │   ├── collection.log
    │   └── replay.sh
    └── reports/
        ├── initial_triage.md
        └── handoff.md
```

The top-level `logs/` and `artifacts/` directories are created but are not currently populated by the primary workflow.

### `manifest/`

Stores execution and case-control records.

- `run_manifest_<run-id>.txt` — JSON-formatted execution metadata, command state, inputs, and input provenance
- `case_manifest_<run-id>.txt` — key-value case summary
- `summary_<run-id>.txt` — key-value workflow status summary

### `evidence/`

Stores original material collected during the investigation.

Raw evidence should not be silently modified or mixed with derived output.

### `derived/`

Stores analytical output generated from original evidence, including:

- filtered extracts;
- reconstructed timelines;
- plots;
- figures;
- and other transformations.

### `commands/`

Intended to record how evidence was collected, transformed, or reproduced.

In v1.1.0, `collection.log` and `replay.sh` are created with placeholder text.

### `reports/`

Stores human-readable investigation artifacts.

`initial_triage.md` is generated with a detailed working template. `handoff.md` is currently placeholder content.

### Disabled manifest artifacts

The source defines writers for:

```text
environment.txt
software_versions.txt
checksums.sha256
```

Their calls are commented out in the current `new` workflow, so the files are not generated in v1.1.0.

## Initial triage report

The generated report is explicitly an initial snapshot, not a final root-cause determination.

It contains:

1. Case control
2. Executive summary
3. Safety and containment
4. Scope
5. Event timeline
6. Reported behavior
7. Known facts
8. Evidence inventory
9. Evidence quality and limitations
10. Unknowns
11. Assumptions requiring validation
12. Initial hypotheses
13. Reproduction plan
14. Immediate actions
15. Escalation and handoff
16. Decision log
17. Exit criteria for initial triage

The template emphasizes observable symptom language, evidence provenance, explicit unknowns, safety disposition, discriminating tests, and a handoff another engineer can continue.

## Safety and execution model

The current runtime includes:

- `set -Eeuo pipefail`;
- a restricted `IFS`;
- centralized fatal exits through `hardstop()`;
- root-shell-only `ERR` reporting;
- root-shell-only cleanup;
- dry-run as the default for controlled operations;
- explicit `--apply` for controlled side effects;
- array-based command execution instead of `eval`;
- quoted argument handling;
- optional replacement through `--force`;
- timestamped backups before replacement;
- separate raw and derived directories;
- and UTC run identifiers.

These controls reduce accidental changes but do not replace operator review, evidence-handling policy, or independent verification.

## Self-test

Run the built-in smoke test:

```bash
./tracehold.sh --self-test
```

Include diagnostic output:

```bash
./tracehold.sh --self-test --verbose
```

The self-test:

- creates a temporary output directory;
- forces apply mode inside that temporary directory;
- exercises the primary `new` workflow;
- checks the generated case, manifests, summary, and initial-triage report;
- and removes the temporary directory after completion.

It is a useful smoke test, not complete command-level coverage. `add`, `collect`, `verify`, `bundle`, completion behavior, and negative validation paths require separate tests.

## Known v1.1.0 limitations

1. **Evidence hashing is source-only.** `add` records the selected source SHA-256, but it does not yet hash and compare the preserved destination.
2. **Evidence ingest is not atomic.** Copying does not yet use a verified temporary destination followed by an atomic final rename.
3. **Provenance remains minimally structured.** The checksum line does not yet record a stable evidence ID, case-relative destination, ingest result, size, collision action, and destination-verification state.
4. **Forced evidence replacement uses backup-and-replace semantics.** A future evidence-specific policy should distinguish identical duplicates from same-name/different-content collisions and prefer preserving both where appropriate.
5. **`collect`, `verify`, and `bundle` are scaffolds.** They do not perform their advertised payload operations.
6. **Environment, software, and checksum-verification generation are disabled.** The helper calls remain commented out or placeholder-only.
7. **Several generated artifacts are placeholders.** This includes `commands/collection.log`, `commands/replay.sh`, and `reports/handoff.md`.
8. **Several fields are not validated.** Timestamp format, reproduction state, status, and confidence accept arbitrary non-option strings.
9. **The run manifest has a `.txt` extension despite JSON content.**
10. **The self-test covers only `new`.** It does not yet provide independent positive and negative tests for every command.
11. **Bash completion must be regenerated after schema changes.** The installed adapter is generated, not rewritten automatically on repository update.

## Troubleshooting

### Nothing was created

Normal operation defaults to dry-run mode.

Add:

```bash
--apply
```

after reviewing the planned actions.

### `jq` is missing

Install `jq` using the package manager appropriate for the host, then verify:

```bash
command -v jq
jq --version
```

The current run-manifest builder requires it.

### The case title created an awkward path

v1.1.0 does not sanitize `--title`. Prefer a slug:

```bash
--title intermittent_link_loss
```

Avoid spaces, slashes, leading dashes, and shell-special characters.

### A multi-value option swallowed later text

`--asset`, `--site`, `--owner`, and `--recent-change` consume values until the next option beginning with `-`.

Correct:

```bash
--owner "V Halcyon" "RF Engineering" \
--status "Open — pending triage"
```

### Values containing spaces were split

Quote each logical value:

```bash
--description "Link dropped during autonomous climb"
--owner "V Halcyon"
--recent-change "Radio firmware updated"
```

### The output directory is unexpected

Inspect the environment:

```bash
printf 'ROOT=%s\n' "${ROOT:-unset}"
printf 'ENGINEERING_DIR=%s\n' "${ENGINEERING_DIR:-unset}"
printf 'OUTPUT_DIR=%s\n' "${OUTPUT_DIR:-unset}"
```

Override it for one run:

```bash
--output-dir /desired/path
```

### Tab completion is not active

Confirm that the completion file exists and is valid:

```bash
completion_file="$HOME/.local/share/bash-completion/completions/tracehold"

ls -l "$completion_file"
bash -n "$completion_file"
```

Load it in the current shell:

```bash
source "$completion_file"
```

Confirm the completion function is registered:

```bash
complete -p tracehold
```

Regenerate it after command-schema changes:

```bash
tracehold --completion bash > "$completion_file"
```

### Case-ID completion shows the wrong case root

Place `--output-dir` before `--case` so completion can resolve the intended root from the words already entered:

```bash
tracehold add --output-dir /desired/cases --case <TAB>
```


### `verify` succeeded but did not report checks

The verification payload is not implemented. Current success only means the scaffolded workflow reached completion.

## Roadmap

> [!NOTE]
> `P0` through `P4` below are **development priorities**, not Tracehold case-severity classifications.
>
> **Dependency path:** P0 Stabilize → P1 Prove Integrity → P2 Complete Workflows → P3 Productize → P4 Integrate

### Current milestone

Tracehold is currently moving from a case-generation scaffold toward a trustworthy evidence-ingest system.

Already implemented or substantially complete:

- [x] discover prior case and run manifests independently of the current invocation's run ID;
- [x] route evidence copies through the apply/dry-run boundary;
- [x] support multiple files in one `add` invocation;
- [x] validate case-ID structure, case directories, manifest directories, evidence type, and source-file existence;
- [x] require explicit `--force` before replacing a same-named evidence destination;
- [x] preserve a timestamped backup during forced replacement;
- [x] capture an initial SHA-256 digest for evidence selected by `add`;
- [x] isolate the current smoke test from normal case storage;
- [x] resolve reusable case and manifest paths before validation and execution.
- [x] centralize command names, required/allowed options, value kinds, aliases, and enums in one shared schema;
- [x] generate command-contract help and Bash completion from that schema.

The next milestone is to turn the current hash capture into a complete integrity transaction:

```text
identify source
    → preflight destination
        → copy atomically
            → verify destination hash
                → record structured provenance
                    → verify later
```

### P0 — Evidence safety and core correctness

**Target release:** `v1.1.1`  
**Goal:** Tracehold cannot silently overwrite evidence, escape its configured case root, emit invalid audit artifacts, or claim completion for work it did not perform.

- [ ] **Preflight the complete `add` batch before the first mutation**
  - Resolve every source and destination.
  - Detect repeated source paths, duplicate basenames, existing destinations, and invalid target directories.
  - **Reason:** A multi-file ingest should either pass preflight as a whole or perform no copies.

- [ ] **Define the final evidence-collision policy**
  - Recommended default: fail.
  - Future explicit policies may include `skip-identical` and `preserve-both`.
  - **Reason:** Two unrelated evidence files may share a basename; replacement should not be the default evidence model.

- [ ] **Confine canonicalized paths beneath `OUTPUT_DIR`**
  - Validate case, manifest, evidence, temporary, and bundle paths.
  - Reject path traversal and symlink escape.
  - **Reason:** User-controlled values must not redirect writes outside the selected case root.

- [ ] **Make evidence copying atomic**
  - Copy into a temporary file on the destination filesystem.
  - Verify the temporary copy.
  - Rename it into its final location only after verification succeeds.
  - Remove temporary files after failure.
  - **Reason:** Interrupted copies must not appear to be valid preserved evidence.

- [ ] **Add a command/option legality matrix**
  - Reject options that are irrelevant to the selected command.
  - **Reason:** Silently ignored options create false operator confidence.

- [ ] **Emit standalone valid JSON artifacts using `.json` extensions**
  - Stop representing JSON manifests as `.txt`.
  - Ensure self-tests never concatenate pretty-printed JSON objects.
  - **Reason:** Artifact type and file extension should agree, and every artifact should be machine-parseable.

- [ ] **Make run summaries truthful**
  - Suggested statuses: `dry_run`, `completed`, `validated_only`, `not_implemented`, `partial`, and `failed`.
  - **Reason:** A successful scaffold or no-op is not a completed collection, verification, or bundle.

- [ ] **Expand self-tests into isolated command tests**
  - Reset command flags, inputs, variadic arrays, derived paths, and run identity for each test.
  - **Reason:** Shared process state can hide invocation-boundary defects.

- [ ] **Add P0 regression coverage**
  - [ ] dry-run performs zero filesystem mutations;
  - [ ] filenames containing spaces, tabs, wildcard characters, and leading dashes are handled safely;
  - [ ] repeated source paths are reported explicitly;
  - [ ] duplicate basenames are reported before copying;
  - [ ] read-only destinations fail before mutation;
  - [ ] path traversal cannot escape `OUTPUT_DIR`;
  - [ ] interrupted copies leave no final evidence artifact;
  - [ ] every generated JSON artifact passes `jq -e .`.

#### P0 exit gate

- [ ] `tracehold add` is trustworthy for evidence that cannot be reacquired.

### P1 — Provenance, hashes, and real verification

**Target release:** `v1.2.0`  
**Goal:** Every evidence object has an inspectable identity, source, preserved destination, integrity record, ingest result, and later verification result.

- [x] **Capture an initial source SHA-256 digest during `add`**
  - Current implementation records the digest beside the selected source path.

- [ ] **Hash and compare both source and preserved destination**
  - Calculate the source digest.
  - Copy the evidence.
  - Calculate the destination digest.
  - Require equality before finalizing the ingest.
  - **Reason:** Hash capture alone does not prove that the preserved copy matches the selected source.

- [ ] **Write provenance only after successful preservation**
  - **Reason:** A failed copy must not leave a record claiming that evidence was added successfully.

- [ ] **Create a canonical evidence index**
  - Suggested artifact: `manifest/evidence_index.json` or append-only `manifest/evidence_events.jsonl`.
  - Record:
    - evidence ID;
    - ingest timestamp and run ID;
    - original and resolved source paths;
    - case-relative destination path;
    - evidence type;
    - size;
    - SHA-256;
    - collision action;
    - copy-verification result;
    - final operation status.
  - **Reason:** A checksum line is useful integrity metadata, but it is only minimal provenance.

- [ ] **Keep the initial case manifest immutable**
  - Store later evidence events in a dedicated index or event stream.
  - **Reason:** Case creation state and later case history are different artifact responsibilities.

- [ ] **Implement the `verify` workflow**
  - Validate required case structure.
  - Validate manifest syntax and schema.
  - Check indexed-file existence.
  - Recalculate and compare hashes.
  - Report modified, missing, unexpected, malformed, and unverifiable evidence separately.
  - **Reason:** Hashing is not complete until Tracehold can consume the recorded hashes later.

- [ ] **Preserve variadic values as JSON arrays**
  - Assets, sites, owners, files, and recent changes should remain arrays.
  - **Reason:** Automation should not have to reverse comma-joined presentation strings.

- [ ] **Separate invocation intent from operation outcome**
  - Run manifest: what was requested.
  - Operation record: what was attempted and what happened.
  - Summary: final status, warnings, counts, and duration.
  - **Reason:** Requested work and completed work are different facts.

- [ ] **Standardize the case manifest as versioned JSON**

- [ ] **Define and test source and destination symlink policy**

#### P1 exit gate

- [ ] `tracehold verify CASE_ID` distinguishes intact, modified, missing, extra, malformed, and unverifiable evidence.

### P2 — Complete the operational workflows

**Target release:** `v1.3.0`  
**Goal:** `collect`, `verify`, and `bundle` perform useful, bounded operations rather than validation-only scaffolding.

- [ ] **Implement collection profiles**
  - `default`
  - `general`
  - `environment`

- [ ] **Harden environment collection**
  - Check optional and required commands.
  - Apply bounded timeouts.
  - Capture stderr and permission failures.
  - Record unavailable fields rather than silently omitting them.
  - Report partial completion explicitly.

- [ ] **Implement software and configuration snapshots**
  - Capture relevant tool versions, service state, Git revision, configuration files, and allowlisted environment data.
  - Record redactions and unavailable sources.

- [ ] **Generate a real `commands/replay.sh`**
  - Use safe quoting.
  - Record collection and derivation commands in execution order.
  - Operate on copied evidence rather than original evidence.

- [ ] **Generate a real `reports/handoff.md`**
  - Include case status, integrity state, evidence inventory, leading hypotheses, unknowns, owners, immediate actions, and next decision.

- [ ] **Implement `bundle`**
  - Verify before bundling.
  - Use a deterministic archive layout.
  - Include a bundle manifest and archive digest.
  - Reject unsafe output locations.
  - Confirm that an extracted bundle verifies identically to the source case.

- [ ] **Model case lifecycle states and legal transitions**
  - Suggested states: `open`, `contained`, `collecting`, `analysis`, `awaiting_action`, `resolved`, and `archived`.

- [ ] **Record workflow outcome metrics**
  - Files attempted, copied, skipped, and failed.
  - Bytes preserved.
  - Hashes verified.
  - Warnings.
  - Duration.
  - Final workflow state.

#### P2 exit gate

- [ ] The complete lifecycle passes:

```text
new → add/collect → verify → handoff → bundle → verify extracted bundle
```

### P3 — Testing, packaging, and operator experience

**Target release:** `v1.4.0`  
**Goal:** Tracehold is maintainable, installable, discoverable, and safe for use by an operator other than its author.

- [ ] Move automated tests into Bats or an equivalent shell-test harness.

- [ ] Add continuous integration:
  - [ ] `bash -n`;
  - [ ] ShellCheck;
  - [ ] `shfmt -d`;
  - [ ] unit tests;
  - [ ] integration tests;
  - [ ] JSON/schema validation;
  - [ ] bundle round-trip verification.

- [ ] Create stable fixture cases:
  - [ ] clean case;
  - [ ] modified evidence;
  - [ ] missing evidence;
  - [ ] duplicate basename;
  - [ ] malformed manifest;
  - [ ] partial collection;
  - [ ] legacy schema.

- [ ] Add installation and uninstall workflows with a configurable prefix.

- [x] Add schema-driven Bash completion.
- [ ] Add optional Zsh and Fish adapters later.

- [ ] Add machine-readable `--json` output for summaries and errors.

- [ ] Publish:
  - README quick start;
  - man page;
  - schema reference;
  - exit-code reference;
  - collection-profile authoring guide;
  - worked examples.

- [ ] Define supported Bash versions, operating systems, and GNU/BSD command differences.

- [ ] Test multi-gigabyte evidence handling without loading file contents into shell variables.

#### P3 exit gate

- [ ] A new operator can install Tracehold, create a case, ingest evidence, verify it, and bundle it using only the published documentation.

### P4 — Traceview and ecosystem integrations

**Target release:** `v2.x`  
**Goal:** Extend Tracehold from a single capture CLI into an evidence, analysis, and reliability ecosystem without losing lineage.

- [ ] **Integrate Traceview**
  - Browse and search cases.
  - Validate schemas.
  - Visualize event timelines.
  - Compare runs and configurations.
  - Inspect evidence lineage.
  - Generate decision-oriented reports.

- [ ] **Add plugin-based collection profiles**
  - UAS/PX4.
  - RF/network.
  - Linux host.
  - Embedded target.
  - CAN.
  - Power and thermal bench.

- [ ] **Add domain importers**
  - `.ulg`;
  - `.tlog`;
  - PCAP;
  - CAN logs;
  - ROS bags;
  - CSV and JSONL;
  - `journalctl` exports;
  - oscilloscope captures.

- [ ] **Build cross-case indexing**
  - Search by asset, site, version, subsystem, error code, hash, symptom, root cause, and regression.

- [ ] **Integrate issue trackers**
  - GitHub Issues and Discussions first.
  - Jira or Linear later.

- [ ] **Support remote or object storage**
  - Content-addressed upload.
  - Resumable transfer.
  - Offline-first queueing.
  - Retention policies.

- [ ] **Add signing and optional encryption**

- [ ] **Generate reliability outputs**
  - Repeated-signature reports.
  - Site and version comparisons.
  - Asset-health features.
  - Failure cemetery.
  - Regression-coverage evidence.

- [ ] **Add redaction and export profiles**
  - Internal.
  - Vendor-safe.
  - Customer-safe.
  - Public.

- [ ] **Add reusable case templates**
  - RF degradation.
  - Intermittent reboot.
  - Estimator divergence.
  - Actuator-authority loss.
  - Thermal fault.
  - Docking failure.

#### P4 exit gate

- [ ] A field symptom can move through capture, analysis, ownership, corrective action, and regression without losing evidence lineage.

### Suggested version sequence

| Version | Primary objective | Release test |
|---|---|---|
| `v1.1.1` | P0 stabilization | Safe multi-file ingest with no silent overwrite, path escape, partial final files, or invalid artifacts |
| `v1.2.0` | P1 provenance and verification | Every indexed artifact is hash-verifiable and schema-valid |
| `v1.3.0` | P2 workflow completion | Full lifecycle through a portable, verified bundle |
| `v1.4.0` | P3 productization | CI, tests, installation, documentation, completions, and machine-readable output |
| `v2.0.0` | P4 Traceview ecosystem | Capture, inspect, correlate, report, and learn across cases |

### Recommended immediate sprint

- [ ] Add `resolve_evidence_destination`.
- [ ] Add batch-wide `preflight_add`.
- [ ] Reject duplicate source paths and duplicate basenames.
- [ ] Refuse existing destinations by default or preserve both explicitly.
- [ ] Copy through a temporary destination.
- [ ] Compare source and destination SHA-256.
- [ ] Record provenance only after the copy is verified.
- [ ] Add a structured evidence index.
- [ ] Implement the first real `verify` pass.
- [ ] Add tests for dry-run, collision, hash mismatch, path escape, and interrupted copy.
- [ ] Rename JSON manifests to `.json`.
- [ ] Bump to `v1.1.1` after the P0 exit gate passes.

#### Immediate sprint definition of done

```text
NEW creates a valid case
ADD preflights the complete batch
ADD copies atomically
ADD verifies source and destination hashes
ADD records structured provenance
VERIFY proves the copy and case structure
DRY-RUN mutates nothing
SELF-TEST produces only valid artifacts
```


## Contributing

Contributions should preserve the project’s core principles:

1. Dry-run remains the default for side-effecting operations.
2. Every side effect obeys the same apply/dry-run boundary.
3. Raw evidence remains distinguishable from derived output.
4. Commands use arrays rather than `eval`.
5. Variables are quoted unless word splitting is intentional.
6. New workflows provide useful failure messages.
7. New artifacts have clear provenance.
8. Documentation distinguishes implemented behavior from planned behavior.
9. Tests cover both successful and failed paths.
10. Evidence collisions are explicit and recoverable.

Before submitting changes:

```bash
bash -n tracehold.sh
./tracehold.sh --help >/dev/null
./tracehold.sh --completion bash | bash -n
./tracehold.sh --self-test --verbose
```

Recommended additional static analysis:

```bash
shellcheck tracehold.sh
```

For a temporary end-to-end `new` test:

```bash
tmp_dir="$(mktemp -d)"

./tracehold.sh new \
    --title smoke_case \
    --description "Documentation smoke test" \
    --severity P4 \
    --asset TEST-001 \
    --output-dir "$tmp_dir" \
    --apply

find "$tmp_dir" -maxdepth 4 -print
rm -rf "$tmp_dir"
```

## Security and evidence handling

`tracehold` may collect system information, logs, identifiers, operational notes, photographs, and other sensitive evidence.

Before sharing or eventually bundling a case:

- review every included file;
- remove secrets and credentials from export copies;
- check logs for tokens, keys, and personal information;
- verify that transfer is authorized;
- preserve an unmodified internal copy where required;
- document any redaction or transformation;
- and follow applicable retention and incident-handling policies.

`tracehold` does not currently provide automatic secret detection, redaction, encryption, access control, or secure deletion.

## License

No license has been selected yet.

Until a license is added, do not assume permission to copy, modify, or redistribute the project beyond rights provided by applicable law.

---

**TRACEHOLD**

Evidence preserved.  
Assumptions documented.  
Unknowns clearly identified.

Maintain the trace until the evidence supports a conclusion.