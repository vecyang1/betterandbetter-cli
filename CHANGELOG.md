# Changelog

All notable changes to the BetterAndBetter (BAB) automation and tooling project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning.

## [1.2.0] - 2026-09-25

### Added
- **Application Rule Cloning & Migration Subcommand (`bab clone` / `bab mimic` / `bab copy`)**:
  - Seamlessly clones or migrates keyboard shortcuts, trackpad gestures, normal mouse actions, and hot corners from one application to another (e.g. `bab clone --from "Google Chrome" --to "ego lite" --reload`).
  - Supports non-destructive merging by default (preserves existing custom application rules), optional `--overwrite` mode, `--only-enabled` filtering, category scoping, atomic locking, pre-mutation backup, and hot-reload.
- **Architectural Streamlining & Snippet Rot Elimination**:
  - Refactored `bin/bab` entrypoint to delegate directly to `bab_core.cli.main`, eliminating redundant duplicated code and ensuring zero drift between root wrapper and core engine.
- **Test Suite Expansion**:
  - Added unit and E2E CLI test coverage for `clone_app_rules` and `bab clone` (56 hermetic tests passing).

## [1.1.0] - 2026-09-25

### Added
- **Rule and Script Deletion Subcommands**:
  - `bab set remove-rule`: safely delete rules by shortcut string or positional index with automatic pre-mutation snapshot and Read-After-Write verification.
  - `bab set remove-script`: safely delete AppleScripts by name or unique ID.
- **Inter-Process Concurrency Locking (`PlistLock`)**:
  - Thread-safe and inter-process mutation locking targeting system temp directory (`/tmp/bab_plist_{hash}.lock`), completely preventing git tree pollution and concurrent race conditions across agents.
- **Microsecond Precision Safety Backups**:
  - Upgraded backup timestamping to `%Y%m%d_%H%M%S_%f` to eliminate snapshot collision on rapid sequential mutations.
- **Enhanced Test Suite**:
  - Added test coverage for `remove_rule`, `remove_applescript`, app alias resolution (`obsidian` -> `md.obsidian`), single-digit shortcut vs index disambiguation, and E2E zero-drift verification (54 tests passing).

### Fixed
- **Premature Lock Release**:
  - Fixed indentation error in `add_or_update_keyboard_rule` where file lock was dropped before mutation and save.
- **Single-Digit Shortcut Collision with List Index**:
  - Fixed issue in `toggle_rule` and `remove_rule` where numeric strings (`"0"`-`"9"`) were erroneously parsed as list indices before testing shortcut matches.
  - Added explicit `index: Optional[int]` parameter and separated CLI `--index` from `--key`.
- **macOS Plist Binary Integrity**:
  - Enforced `plistlib.FMT_BINARY` preservation during atomic writes, preventing XML low-ASCII control character exceptions.
- **Deep Diff & Explain Drift Detection**:
  - Replaced collision-prone dictionary indexing with multi-pass ordered reconciliation engine, eliminating false-positive `MODIFIED_ACTION` warnings on identical rules with duplicate or empty `{}` gestures.

## [1.0.0] - 2026-09-25

### Added
- **Unified Agentic CLI (`bab`)**:
  - Installed executable at `bin/bab` and exposed global symlink at `~/.local/bin/bab` for seamless cross-agent and operator usage.
  - Subcommands: `status`, `inspect`, `explain` (`diagnose`), `diff`, `sync`, `set`, `backup`, `reload`.
  - Machine-readable `--json` output across all primary commands for subagents and pipelines.
- **Diagnostic-First Engine (`bab explain`)**:
  - Real-time diagnostic evaluation for shortcuts (e.g. `⌘B`), apps (e.g. `Obsidian`, `Antigravity`, `ego lite`), gestures, and actions.
  - Precedence and Shadowing Analysis: clearly articulates when an application-specific rule overrides or shadows global `[All Applications]` rules, and explains fallback behavior for unconfigured applications.
  - Drift Detection: detects unsaved or unsynced rule deviations between macOS Live preferences and Git backup repository.
- **Deep Reconciliation & Inspector (`bab diff` & `bab inspect`)**:
  - Live vs Git structural diffing covering modified rules, added/removed applications, and script changes.
  - Multi-category inspection across keyboard shortcuts, trackpad gestures, magic mouse, normal mouse, hot corners, and AppleScript library.
- **Safety Invariant Mutation Engine (`bab set`)**:
  - Programmatic creation and modification of rules, state toggles, and AppleScripts.
  - Mandatory pre-mutation automatic backup to `~/.bab_backups/`.
  - Atomic write via temporary file replacement and Read-After-Write verification.
  - Instant hot-reload via `--reload` with `cfprefsd` cache flushing and safe process restart.
- **Comprehensive Test Suite**:
  - 43 automated unit, contract, and E2E tests in `tests/` (`test_keycodes.py`, `test_plist_manager.py`, `test_inspector.py`, `test_diagnostic.py`, `test_modifier.py`, `test_edge_cases.py`, `test_cli_e2e.py`).
- **Comprehensive Documentation**:
  - Updated `README.md` detailing SSOT architecture, contracts, command usage, and safety invariants.
