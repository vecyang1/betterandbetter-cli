# betterandbetter-cli (`bab`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tests: 54 Passing](https://img.shields.io/badge/tests-54%20passing-brightgreen.svg?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![macOS Compatible](https://img.shields.io/badge/macOS-12.0+-black.svg?style=for-the-badge&logo=apple&logoColor=white)](https://www.apple.com/macos/)

> **Diagnostic-First CLI, Headless Configuration Engine & Automation Controller for [BetterAndBetter (BAB)](https://www.better365.cn/BetterAndBetter.html) on macOS.**

---

> [!IMPORTANT]
> **AI-Native Engineering Provenance / 智能工程溯源说明**
> 
> - **EN**: This repository was engineered from inception to production using advanced autonomous AI agent pair programming. All architectural specifications, binary property list serialization, Carbon virtual keycode mappings, inter-process concurrency locking, regression test suites (54 hermetic tests), and diagnostic engines were researched, planned, implemented, and verified end-to-end against real live macOS runtimes without artificial mocks.
> - **ZH**: 本项目由开发者与高级 AI 编程 Agent 协同端到端工程化构建。全套架构设计、macOS 二进制属性列表编解码、Carbon 键码解析、跨进程排他锁、54 项回归测试及“对账器优先（Diagnostic-First）”引擎，均直接对照真实 macOS 运行时与真实配置对账生成并实体验证。

---

## 💡 Why This Wheel Exists / 为什么需要它

[BetterAndBetter (BAB)](https://www.better365.cn/BetterAndBetter.html) is an exceptional, industry-favorite gesture and shortcut utility for macOS, enabling granular touchpad gestures, mouse enhancements, keyboard shortcuts, window snapping, and AppleScript triggers.

However, power users and AI agents frequently encounter friction when managing complex configurations:
- **No Headless Automation**: Configuring dozens of apps requires repetitive manual clicking in GUI panels.
- **Ghost Logic & Drift**: "Why didn't my shortcut trigger?" — Difficult to know if an application rule was shadowed by a global rule, or whether a local change actually applied.
- **Configuration Fragility**: Hand-editing macOS preference files risks XML serialization failure, dropping low-ASCII control characters, or race conditions during multi-process edits.

`betterandbetter-cli` (`bab`) solves this by providing a unified, battle-tested, diagnostic-first CLI tool for both human operators and autonomous AI agents.

---

## 🏛️ Architecture & Single Source of Truth (SSOT)

```
┌────────────────────────────────────────────────────────────────────────┐
│                   BetterAndBetter (BAB) Dataflow & SSOT                │
├────────────────────────────────────────────────────────────────────────┤
│  [Runtime Truth (Live)]  ~/Library/Preferences/cn.better365.BetterAndBetter.plist
│         ▲                                                  │           │
│    (Write: Atomic + Read-After-Write)                  (Read: Pure)    │
│         │                                                  ▼           │
│  [Unified CLI Console] ──> bab (Status, Inspect, Explain, Mutate, Sync)│
│         │                                                  │           │
│  (Microsecond Snapshots)                               (Reconciliation)│
│         ▼                                                  ▼           │
│  [Safety Rollbacks] ~/.bab_backups/          [Versioned Repo] Git Backup│
└────────────────────────────────────────────────────────────────────────┘
```

1. **Runtime Truth (Live)**: `~/Library/Preferences/cn.better365.BetterAndBetter.plist` is the authoritative contract read by the BetterAndBetter daemon.
2. **Deterministic Mutation**: All writes acquire an OS-level file lock, create microsecond-timestamped snapshots in `~/.bab_backups/`, use atomic file replacement, and immediately perform Read-After-Write verification.
3. **Diagnostic-First (`explain`)**: Direct symbol execution against live preferences — never guesses or simulates mock rules.

---

## ⚡ Quick Start / 快速上手

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/vecyang1/betterandbetter-cli.git
cd betterandbetter-cli

# Symlink executable to your PATH
ln -sf "$(pwd)/bin/bab" ~/.local/bin/bab

# Verify installation
bab status
```

Or install via Python:

```bash
pip install -e .
bab --help
```

---

## 🛠️ CLI Showcase & Commands / 功能速查

### 1. System Status (`bab status`)

Inspect live daemon status, PID, preference sizes, and summary statistics across all 6 rule categories:

```bash
$ bab status
================================================================================
                     BetterAndBetter (BAB) 系统与配置状态
================================================================================
应用安装状态 : ✅ 已安装
应用版本     : 2.7.9 (/Applications/BetterAndBetter.app)
主进程运行   : 🟢 运行中 (PID: 13643)
辅助进程运行 : 🟢 运行中 (PID: 2507)
--------------------------------------------------------------------------------
Live 本地配置: ✅ 存在 (174,168 bytes)
Git 仓库备份 : ✅ 存在 (174,189 bytes)
对账同步状态 : ✅ 完全同步 (一致)
--------------------------------------------------------------------------------
配置概览     : 已配置应用 41 个 | 规则总数 523 条 (生效中: 391)

规则分类    | 分类名称                                 | 规则总数 | 已启用 | 启用率
------------+------------------------------------------+------+-----+-------
keyboard    | 键盘快捷键 (Keyboard Shortcuts)          | 300  | 233 | 77.7% 
trackpad    | 触控板手势 (Trackpad Gestures)           | 145  | 92  | 63.4% 
magicmouse  | 妙控鼠标手势 (Magic Mouse Gestures)      | 11   | 11  | 100.0%
normalmouse | 普通鼠标操作 (Normal Mouse Actions)      | 42   | 42  | 100.0%
hotcorners  | 屏幕触发角 (Hot Corners)                 | 25   | 13  | 52.0% 
applescript | AppleScript 脚本库 (AppleScript Library) | 27   | 27  | 100.0%
================================================================================
```

---

### 2. Diagnostic-First Evaluation (`bab explain` / `bab diagnose`)

Never guess why a shortcut or gesture behaves the way it does. Enter any shortcut, application name, gesture string, or action keyword:

```bash
# Diagnose shortcut precedence and shadowing across all apps
bab explain "⌘B"

# Diagnose a specific application's active rules and global fallback behavior
bab explain "ego lite"
bab explain "Obsidian"
bab explain "Path Finder"

# Diagnose trackpad gesture mappings
bab explain "3Finger_Tap"

# Machine-readable JSON output for automated subagents
bab explain "⌘B" --json
```

**Sample Output (`bab explain "ego lite"`):**
```text
================================================================================
                 BetterAndBetter 诊断报告: 【ego lite】
================================================================================
诊断目标类型 : APP
--------------------------------------------------------------------------------
【1. 匹配规则与对账状态】
应用                   | 分类       | 触发方式 | 动作类型 | 执行动作                                  | 当前状态 | Git对账状态
-----------------------+------------+------+--------+-------------------------------------------+---------+--------
com.citrolabs.ego.lite | 键盘快捷键 | ⌘B   | Preset | Click the menu title "/Tab/Duplicate Tab" | ✅ 启用 | ✅ 一致

【2. 真实生效与优先级分析】
诊断结论：应用 【com.citrolabs.ego.lite】 共配置了 1 条规则（已启用: 1，已禁用: 0）。
- 在该应用激活时，这些专属规则优先级高于全局规则。
- 未被上述规则覆盖的其余手势与快捷键，继续继承 [All Applications] 全局规则。

【3. 备份与状态漂移分析】
✅ 所有匹配规则均与 Git 备份保持严格一致，无状态漂移。
================================================================================
```

---

### 3. Multi-Category Inspection (`bab inspect`)

```bash
# List all configured applications and rule count
bab inspect apps

# Filter keyboard rules by application
bab inspect keyboard --app obsidian

# Filter trackpad gestures (enabled only)
bab inspect trackpad --app "pdf expert" --enabled-only

# List custom AppleScripts
bab inspect applescript
```

---

### 4. Safe Configuration Modification (`bab set`)

All mutations execute under cross-process locking with automatic microsecond snapshotting and atomic replacement:

```bash
# Add or update a keyboard shortcut rule (auto-reloading daemon)
bab set rule --app "com.google.antigravity" --key "⌘K" --action-type Preset --action Center --reload

# Enable or disable a rule by shortcut or positional index
bab set toggle --app "md.obsidian" --key "⌘R" --disable --reload
bab set toggle --app "md.obsidian" --index 0 --enable --reload

# Safely remove a rule
bab set remove-rule --app "com.google.antigravity" --key "⌘K" --reload

# Add a custom AppleScript to the library
bab set script --name "Clear Safari Cache" --code "tell application \"Safari\" to do something"

# Remove an AppleScript by name or unique ID
bab set remove-script --name "Clear Safari Cache"
```

---

### 5. Application Rule Cloning & Migration (`bab clone` / `bab mimic`)

Easily clone or migrate shortcuts, trackpad gestures, and mouse actions from one application to another (e.g. from Google Chrome to Ego Browser):

```bash
# Clone active rules from Chrome to Ego Browser, non-destructively merging and hot-reloading
bab clone --from "Google Chrome" --to "ego lite" --only-enabled --reload

# Clone with overwrite mode
bab clone --from "Google Chrome" --to "ego lite" --overwrite --reload

# Clone only specific categories (e.g., keyboard only)
bab clone --from "Google Chrome" --to "ego lite" --category keyboard --reload
```

---

### 6. Reconciliation & Sync (`bab diff` / `bab sync`)

```bash
# Diff live preferences against git backup
bab diff

# Export live preferences to backup directory
bab sync --to-git

# Restore backup to live preferences and hot-reload
bab sync --to-live --reload

# Clean hot-reload of BetterAndBetter process
bab reload
```

---

## 🔒 Safety Invariants / 安全保证

1. **Concurrency Protection (`PlistLock`)**: Uses kernel-level `fcntl.flock` on `/tmp/bab_plist_{hash}.lock` to prevent multi-process write races.
2. **Microsecond Precision Snapshots**: Automatic pre-mutation snapshots saved to `~/.bab_backups/` using `%Y%m%d_%H%M%S_%f`.
3. **Binary Plist Integrity**: Enforces `plistlib.FMT_BINARY` preservation during serialization, preventing XML low-ASCII control character corruption.
4. **Read-After-Write Verification**: After atomic disk write, the file is re-read and parsed to guarantee zero data loss before releasing the lock.
5. **Cache Invalidation**: Automatically flushes macOS `cfprefsd` preference daemon before restarting the application.

---

## 📂 Project Structure / 真实目录结构

```text
betterandbetter-cli
├── CHANGELOG.md             # Semantic version history (v1.0.0, v1.1.0)
├── LICENSE                  # MIT License
├── README.md                # Comprehensive documentation & showcase
├── pyproject.toml           # Standard Python packaging configuration
├── bin
│   └── bab                  # Executable CLI entrypoint
├── bab_core                 # Modular core implementation
│   ├── __init__.py
│   ├── cli.py               # Argument parsing and command handlers
│   ├── constants.py         # SSOT paths, bitmasks, keycodes, aliases
│   ├── diagnostic.py        # Diagnostic-first explain engine & shadowing
│   ├── inspector.py         # Multi-category inspection engine
│   ├── keycodes.py          # Carbon / Cocoa virtual keycode parser
│   ├── models.py            # Typed dataclasses & schemas
│   ├── modifier.py          # Mutation engine with concurrency locking
│   ├── plist_manager.py     # Binary plist IO, atomic writes & diff
│   └── sync.py              # Git reconciliation and sync engine
└── tests                    # 54 hermetic unit and E2E regression tests
    ├── fixtures
    ├── test_cli_e2e.py      # End-to-end CLI command verification
    ├── test_diagnostic.py   # Diagnostic engine & shadowing tests
    ├── test_edge_cases.py   # Corrupted plist, special Unicode & error bounds
    ├── test_inspector.py    # Inspection & app resolution tests
    ├── test_keycodes.py     # Modifier bitmask & shortcut parser tests
    ├── test_modifier.py     # Concurrency lock, mutation & deletion tests
    └── test_plist_manager.py# Binary IO & ordered diff reconciliation tests
```

---

## 🧪 Automated Testing / 自动化测试

Run the full test suite locally:

```bash
python3 -m unittest discover -s tests -v
```

Output:
```text
Ran 54 tests in 1.294s

OK
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Copyright (c) 2026 Vec Yang.
