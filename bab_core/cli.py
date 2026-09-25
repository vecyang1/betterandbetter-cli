#!/usr/bin/env python3
"""
BetterAndBetter (BAB) CLI
Unified, diagnostic-first management and inspection tool for BetterAndBetter on macOS.
"""

import argparse
import json
import os
import sys

# Ensure bab_core is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bab_core.constants import (
    LIVE_PREFS_PATH,
    REPO_DIR,
    REPO_PREFS_PATH,
    RULE_CATEGORIES,
    RULE_CATEGORY_TITLES,
)
from bab_core.daemon import (
    get_daemon_status,
    install_daemon,
    uninstall_daemon,
)
from bab_core.diagnostic import explain_query
from bab_core.inspector import (
    get_status,
    inspect_rules,
    inspect_scripts,
    list_configured_apps,
)
from bab_core.modifier import (
    add_or_update_applescript,
    add_or_update_keyboard_rule,
    clone_app_rules,
    remove_applescript,
    remove_rule,
    toggle_rule,
)
from bab_core.plist_manager import (
    diff_plists,
    load_plist,
    restart_bab,
)
from bab_core.sync import (
    run_backup,
    sync_git_to_live,
    sync_live_to_git,
)


def _format_table(headers: list, rows: list) -> str:
    """Format tabular data with automatic column width adjustment."""
    if not rows:
        return "(无数据)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            # calculate visual width (handles basic CJK width)
            val_str = str(val)
            visual_len = sum(2 if ord(c) > 127 else 1 for c in val_str)
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], visual_len)

    def pad_cell(text, width):
        vlen = sum(2 if ord(c) > 127 else 1 for c in str(text))
        return str(text) + " " * max(0, width - vlen)

    header_line = " | ".join(pad_cell(h, col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(pad_cell(row[i] if i < len(row) else "", col_widths[i]) for i in range(len(headers)))
        for row in rows
    ]
    return f"{header_line}\n{sep_line}\n" + "\n".join(row_lines)


def cmd_status(args):
    """Handle `bab status` command."""
    status = get_status(
        live_path=getattr(args, "live_file", LIVE_PREFS_PATH),
        git_path=getattr(args, "git_file", REPO_PREFS_PATH),
    )

    if args.json:
        print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
        return

    print("================================================================================")
    print("                     BetterAndBetter (BAB) 系统与配置状态")
    print("================================================================================")
    print(f"应用安装状态 : {'✅ 已安装' if status.app_installed else '❌ 未检测到'}")
    print(f"应用版本     : {status.app_version} ({status.app_path})")
    print(
        f"主进程运行   : {'🟢 运行中 (PID: ' + str(status.app_pid) + ')' if status.app_running else '🔴 未运行'}"
    )
    print(
        f"辅助进程运行 : {'🟢 运行中 (PID: ' + str(status.helper_pid) + ')' if status.helper_running else '🔴 未运行'}"
    )
    print("--------------------------------------------------------------------------------")
    print(
        f"Live 本地配置: {'✅ 存在' if status.live_plist_exists else '❌ 缺失'} "
        f"({status.live_plist_size:,} bytes | 更新于: {status.live_plist_mtime or 'N/A'})"
    )
    print(
        f"Git 仓库备份 : {'✅ 存在' if status.git_plist_exists else '❌ 缺失'} "
        f"({status.git_plist_size:,} bytes | 更新于: {status.git_plist_mtime or 'N/A'})"
    )
    print(
        f"对账同步状态 : {'✅ ' + status.diff_summary if status.is_synced else '⚠️ ' + status.diff_summary}"
    )
    print("--------------------------------------------------------------------------------")
    print(f"配置概览     : 已配置应用 {status.total_apps} 个 | 规则总数 {status.total_rules} 条 (生效中: {status.total_enabled})")

    headers = ["规则分类", "分类名称", "规则总数", "已启用", "启用率"]
    rows = []
    for slug, key in RULE_CATEGORIES.items():
        st = status.category_stats.get(slug, {"total": 0, "enabled": 0})
        total = st["total"]
        en = st["enabled"]
        pct = f"{(en / total * 100):.1f}%" if total > 0 else "N/A"
        rows.append([slug, RULE_CATEGORY_TITLES.get(key, key), total, en, pct])

    print("\n" + _format_table(headers, rows))

    # LaunchAgent Daemon Observability
    daemon = status.daemon_status
    if daemon:
        print("--------------------------------------------------------------------------------")
        d_loaded = daemon.get("loaded", False)
        d_installed = daemon.get("installed", False)
        if d_loaded:
            pid_info = f" (PID: {daemon['pid']})" if daemon.get("pid") else " (空闲待命中)"
            daemon_status_text = f"🟢 正常运行中{pid_info}"
        elif d_installed:
            daemon_status_text = "🟡 已配置但未加载 (运行 `bab backup --install-daemon` 激活)"
        else:
            daemon_status_text = "🔴 未安装守护进程 (运行 `bab backup --install-daemon` 安装)"

        print(f"自动备份守护 : {daemon_status_text}")
        print(f"守护服务标识 : {daemon.get('label', 'N/A')}")

        triggers = []
        if daemon.get("watch_paths"):
            triggers.append(f"文件变更监听 (WatchPaths: {len(daemon['watch_paths'])} 个路径, 节流 {daemon.get('throttle_interval', 30)}s)")
        if daemon.get("calendar_interval"):
            cal = daemon["calendar_interval"]
            h = cal.get("Hour", 11)
            m = cal.get("Minute", 0)
            triggers.append(f"每日计划 {h:02d}:{m:02d}")
        if triggers:
            print(f"双重触发机制 : {' + '.join(triggers)}")

        receipt = daemon.get("receipt")
        if receipt:
            rec_status = receipt.get("status", "unknown")
            rec_icon = "✅" if rec_status in ("success", "no_changes") else "⚠️"
            rec_time = receipt.get("completed_at", "N/A")
            rec_commit = (receipt.get("commit") or "")[:9]
            commit_info = f" | Commit: {rec_commit}" if rec_commit else ""
            print(f"最近自动备份 : {rec_icon} {rec_status} ({rec_time}{commit_info})")
            if receipt.get("message"):
                print(f"最新备份说明 : {receipt['message']}")
        elif daemon.get("recent_logs"):
            print(f"最新备份日志 : {daemon['recent_logs'][-1]}")
    print("================================================================================")


def cmd_inspect(args):
    """Handle `bab inspect` command."""
    target_path = REPO_PREFS_PATH if args.source == "git" else LIVE_PREFS_PATH
    if not os.path.exists(target_path):
        print(f"错误: 目标文件不存在: {target_path}", file=sys.stderr)
        sys.exit(1)

    data = load_plist(target_path)

    # 1. Inspect AppleScripts
    if args.category == "applescript":
        scripts = inspect_scripts(data, search=args.app)
        if args.json:
            print(json.dumps([s.to_dict() for s in scripts], ensure_ascii=False, indent=2))
            return
        headers = ["ID (前8位)", "脚本名称", "代码预览", "修改状态", "备注"]
        rows = [
            [s.id[:8] + "...", s.name, (s.script[:40].replace("\n", " ") + "..."), "已修改" if s.edited else "默认", s.note]
            for s in scripts
        ]
        print(f"\n[BetterAndBetter AppleScript 脚本库 (共 {len(scripts)} 个)]")
        print(_format_table(headers, rows))
        return

    # 2. Inspect configured apps list if category is 'apps'
    if args.category == "apps" or (not args.category and not args.app and not args.enabled_only):
        apps = list_configured_apps(data)
        if args.json:
            print(json.dumps([a.to_dict() for a in apps], ensure_ascii=False, indent=2))
            return
        headers = ["应用名称 / Bundle ID", "规则总数", "已启用数", "覆盖分类"]
        rows = [
            [a.display_name, a.total_rules, a.enabled_rules, ", ".join(k.replace("ruleOf", "") for k in a.categories.keys())]
            for a in apps
        ]
        print(f"\n[BetterAndBetter 已配置应用列表 (共 {len(apps)} 个)]")
        print(_format_table(headers, rows))
        print("\n提示: 使用 `bab inspect --app <应用名>` 查看特定应用的详细规则，或 `bab explain <应用名>` 查看诊断。")
        return

    # 3. Inspect detailed rules
    rules = inspect_rules(
        data,
        category_filter=args.category if args.category != "apps" else None,
        app_filter=args.app,
        enabled_only=args.enabled_only,
    )

    if args.json:
        print(json.dumps([r.to_dict() for r in rules], ensure_ascii=False, indent=2))
        return

    headers = ["#", "应用", "分类", "触发方式", "动作类型", "执行动作", "状态", "备注"]
    rows = []
    for r in rules:
        status_icon = "✅ 启用" if r.enabled else "❌ 禁用"
        cat_short = r.category.replace("ruleOf", "")
        rows.append([
            r.index + 1,
            r.app,
            cat_short,
            r.gesture_display,
            r.action_type,
            r.action_display,
            status_icon,
            r.note,
        ])

    title = f"BetterAndBetter 规则明细 (共 {len(rules)} 条"
    if args.app:
        title += f" | 筛选应用: {args.app}"
    if args.category:
        title += f" | 筛选分类: {args.category}"
    if args.enabled_only:
        title += " | 仅已启用"
    title += f" | 数据源: {args.source})"

    print(f"\n[{title}]")
    print(_format_table(headers, rows))


def cmd_explain(args):
    """Handle `bab explain` / `bab diagnose` command."""
    if not os.path.exists(LIVE_PREFS_PATH):
        print(f"错误: Live 偏好文件不存在: {LIVE_PREFS_PATH}", file=sys.stderr)
        sys.exit(1)

    live_data = load_plist(LIVE_PREFS_PATH)
    git_data = load_plist(REPO_PREFS_PATH) if os.path.exists(REPO_PREFS_PATH) else None

    result = explain_query(args.query, live_data, git_data)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    print("================================================================================")
    print(f"                 BetterAndBetter 诊断报告: 【{args.query}】")
    print("================================================================================")
    print(f"诊断目标类型 : {result.query_intent}")
    print("--------------------------------------------------------------------------------")
    print("【1. 匹配规则与对账状态】")
    if result.matched_rules:
        headers = ["应用", "分类", "触发方式", "动作类型", "执行动作", "当前状态", "Git对账状态"]
        rows = []
        for r in result.matched_rules:
            en_str = "✅ 启用" if r["enabled"] else "❌ 禁用"
            drift_icon = "✅ 一致" if r["drift_status"] == "SYNCHRONIZED" else f"⚠️ {r['drift_status']}"
            rows.append([
                r["app"],
                r["category_title"].split()[0],
                r["trigger"],
                r["action_type"],
                r["action"],
                en_str,
                drift_icon,
            ])
        print(_format_table(headers, rows))
    else:
        print("未检测到直接匹配的专属规则。")

    if result.matched_scripts:
        print("\n【匹配的 AppleScript 脚本】")
        headers = ["脚本ID", "脚本名称", "代码片段", "备注"]
        rows = [
            [s["id"][:8] + "...", s["name"], s["code_snippet"], s["note"]]
            for s in result.matched_scripts
        ]
        print(_format_table(headers, rows))

    print("\n【2. 真实生效与优先级分析】")
    print(result.shadowing_explanation)

    print("\n【3. 备份与状态漂移分析】")
    print(result.drift_explanation)

    if result.actionable_recommendations:
        print("\n【4. 推荐操作与修复指引】")
        for rec in result.actionable_recommendations:
            print(f"- {rec}")
    print("================================================================================")


def cmd_diff(args):
    """Handle `bab diff` command."""
    if not os.path.exists(LIVE_PREFS_PATH):
        print(f"错误: Live 偏好文件不存在: {LIVE_PREFS_PATH}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(REPO_PREFS_PATH):
        print(f"错误: Git 备份文件不存在: {REPO_PREFS_PATH}", file=sys.stderr)
        sys.exit(1)

    live_data = load_plist(LIVE_PREFS_PATH)
    git_data = load_plist(REPO_PREFS_PATH)
    diff = diff_plists(live_data, git_data)

    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
        return

    print("================================================================================")
    print("           BetterAndBetter 对账器: Live 本地配置 vs Git 备份仓库")
    print("================================================================================")
    if diff["is_synced"]:
        print("✅ 状态完全一致！Live preferences 与 Git 备份仓库无任何漂移。")
        print("================================================================================")
        return

    print("⚠️ 检测到配置状态漂移 (Live 本地与 Git 备份存在差异):\n")
    for item in diff["summary"]:
        print(f"  • {item}")

    print("\n【明细分析】")
    for cat_key, cdiff in diff["categories"].items():
        cat_title = RULE_CATEGORY_TITLES.get(cat_key, cat_key)
        print(f"\n[{cat_title}]")
        if cdiff["apps_only_in_live"]:
            print(f"  + 仅在 Live 中存在应用: {', '.join(cdiff['apps_only_in_live'])}")
        if cdiff["apps_only_in_git"]:
            print(f"  - 仅在 Git 中存在应用: {', '.join(cdiff['apps_only_in_git'])}")
        for app, chg in cdiff["apps_with_changes"].items():
            print(f"  ~ 应用 [{app}]: Live={chg['live_count']} 条, Git={chg['git_count']} 条")
            for m in chg.get("modified_details", []):
                for f, vals in m["changes"].items():
                    print(f"    - 规则 {m['gesture']}: 字段 [{f}] Live={vals['live']} vs Git={vals['git']}")

    print("\n【建议动作】")
    print("  • 如需固化本地 Live 修改到 Git 仓库: 请执行 `bab sync --to-git` 或 `bab backup`")
    print("  • 如需还原 Git 仓库配置到本地 Live:   请执行 `bab sync --to-live --reload`")
    print("================================================================================")


def cmd_sync(args):
    """Handle `bab sync` command."""
    if args.to_live:
        if not args.json:
            print(f"正在从 Git 仓库恢复配置到 Live 本地偏好... (dry_run={args.dry_run})")
        res = sync_git_to_live(dry_run=args.dry_run, reload_bab=args.reload)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 恢复操作完成！")
            if res.get("backup_files"):
                print(f"已创建恢复前安全备份: {', '.join(res['backup_files'])}")
            if res.get("reloaded"):
                print("✅ 已自动重启 BetterAndBetter 进程使配置生效。")
    else:
        if not args.json:
            print(f"正在将 Live 本地偏好同步到 Git 仓库... (dry_run={args.dry_run})")
        res = sync_live_to_git(dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 同步完成！已将 Live 配置写入: {REPO_DIR}")
            print("提示: 运行 `bab backup` 可一键创建 Git 提交并推送到远端。")


def cmd_backup(args):
    """Handle `bab backup` command."""
    if getattr(args, "daemon_status", False):
        st = get_daemon_status()
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
            return
        print("================================================================================")
        print("                 BetterAndBetter 自动备份守护进程 (LaunchAgent)")
        print("================================================================================")
        print(f"服务 Label   : {st['label']}")
        print(f"配置文件     : {st['plist_path']} ({'✅ 存在且有效' if st['plist_valid'] else ('⚠️ 损坏' if st['installed'] else '❌ 未安装')})")
        print(f"运行状态     : {'🟢 已加载至 launchd' if st['loaded'] else '🔴 未加载'}")
        if st.get("pid"):
            print(f"进程 PID     : {st['pid']}")
        if st.get("last_exit_code") is not None:
            print(f"上次退出码   : {st['last_exit_code']}")
        if st.get("legacy_detected"):
            print("⚠️ 注意: 检测到遗留旧版守护进程 (com.user.betterandbetter-backup)，建议使用 --install-daemon 清理升级。")
        print("--------------------------------------------------------------------------------")
        print("【触发机制】")
        if st.get("watch_paths"):
            print("  • WatchPaths (变更实时触发):")
            for wp in st["watch_paths"]:
                print(f"    - {wp}")
            print(f"  • ThrottleInterval (防抖节流保护): {st.get('throttle_interval', 30)} 秒")
        if st.get("calendar_interval"):
            cal = st["calendar_interval"]
            print(f"  • StartCalendarInterval (兜底定时): 每日 {cal.get('Hour', 11):02d}:{cal.get('Minute', 0):02d}")
        print("--------------------------------------------------------------------------------")
        print("【最近备份凭据】")
        if st.get("receipt"):
            rc = st["receipt"]
            print(f"  • 状态: {rc.get('status')}")
            print(f"  • 完成时间: {rc.get('completed_at')}")
            print(f"  • Commit: {rc.get('commit') or '无新变更'}")
            print(f"  • 说明: {rc.get('message')}")
        else:
            print("  • 尚无备份凭据")
        if st.get("recent_logs"):
            print("--------------------------------------------------------------------------------")
            print("【最近备份日志】")
            for line in st["recent_logs"]:
                print(f"  {line}")
        print("================================================================================")
        return

    if getattr(args, "install_daemon", False):
        try:
            res = install_daemon(force=getattr(args, "force", False))
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"✅ {res['message']}")
                print(f"服务 Label : {res['details']['label']}")
                print(f"配置文件   : {res['details']['plist_path']}")
                print(f"加载状态   : {'🟢 运行中' if res['details']['loaded'] else '🔴 未运行'}")
        except Exception as e:
            print(f"❌ 安装守护进程失败: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if getattr(args, "uninstall_daemon", False):
        try:
            res = uninstall_daemon()
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"✅ {res['message']}")
        except Exception as e:
            print(f"❌ 卸载守护进程失败: {e}", file=sys.stderr)
            sys.exit(1)
        return

    print("正在执行 BetterAndBetter 备份与 Git 提交...")
    res = run_backup()
    if res["returncode"] == 0:
        print("✅ 备份执行完成！")
        if res.get("log_messages"):
            for line in res["log_messages"].splitlines():
                print(f"  • {line}")
        elif res["stdout"].strip():
            print(res["stdout"].strip())
    else:
        print(f"❌ 备份执行失败 (退出码 {res['returncode']}):", file=sys.stderr)
        if res.get("stderr"):
            print(res["stderr"], file=sys.stderr)
        if res.get("stdout"):
            print(res["stdout"], file=sys.stderr)
        sys.exit(res["returncode"])


def cmd_reload(args):
    """Handle `bab reload` command."""
    print("正在重启 BetterAndBetter 应用程序...")
    success = restart_bab()
    if success:
        print("✅ BetterAndBetter 已成功重启！")
    else:
        print("❌ 重启失败，请检查应用程序权限或手动打开 /Applications/BetterAndBetter.app", file=sys.stderr)
        sys.exit(1)


def cmd_set(args):
    """Handle `bab set` subcommands."""
    target_path = REPO_PREFS_PATH if args.target == "git" else LIVE_PREFS_PATH

    if args.set_type == "rule":
        if not args.key:
            print("错误: 请通过 --key 指定快捷键 (例如: '⌘B', 'cmd+b', '⇧⌘N')", file=sys.stderr)
            sys.exit(1)
        if not args.action:
            print("错误: 请通过 --action 指定执行动作 (例如: 'Half_of_Top', '⌘C')", file=sys.stderr)
            sys.exit(1)

        en = False if args.disable else True
        try:
            res = add_or_update_keyboard_rule(
                plist_path=target_path,
                app_name=args.app,
                key_str=args.key,
                action_type=args.action_type,
                action_value=args.action,
                enable=en,
                note=args.note or "",
                reload_bab=args.reload,
            )
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                op_zh = "新增" if res["operation"] == "added" else "更新"
                print(f"✅ 成功{op_zh}规则: [{res['app']}] {res['shortcut']} -> {res['action_type']}: {res['action']} (启用: {res['enable']})")
                print(f"安全备份已保存至: {res['backup_file']}")
                if res.get("reloaded"):
                    print("✅ BetterAndBetter 进程已自动重新加载。")
        except Exception as e:
            print(f"❌ 规则设置失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.set_type == "toggle":
        if args.index is not None:
            idx_val = args.index
            key_val = ""
            target_label = f"索引 #{args.index}"
        elif args.key is not None:
            idx_val = None
            key_val = args.key
            target_label = f"快捷键/手势 '{args.key}'"
        else:
            print("错误: 请通过 --key 或 --index 指定要切换的规则", file=sys.stderr)
            sys.exit(1)

        explicit_en = None
        if args.enable:
            explicit_en = True
        elif args.disable:
            explicit_en = False

        try:
            res = toggle_rule(
                plist_path=target_path,
                app_name=args.app,
                category=args.category,
                key_or_index=key_val,
                index=idx_val,
                enable=explicit_en,
                reload_bab=args.reload,
            )
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                en_str = "已启用" if res["new_enable"] else "已禁用"
                print(f"✅ 状态变更成功: [{res['app']}] 规则 {target_label} 当前状态 -> 【{en_str}】")
                print(f"安全备份已保存至: {res['backup_file']}")
                if res.get("reloaded"):
                    print("✅ BetterAndBetter 进程已自动重新加载。")
        except Exception as e:
            print(f"❌ 状态变更失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.set_type == "remove-rule":
        if args.index is not None:
            idx_val = args.index
            key_val = ""
            target_label = f"索引 #{args.index}"
        elif args.key is not None:
            idx_val = None
            key_val = args.key
            target_label = f"快捷键/手势 '{args.key}'"
        else:
            print("错误: 请通过 --key 或 --index 指定要删除的规则", file=sys.stderr)
            sys.exit(1)

        try:
            res = remove_rule(
                plist_path=target_path,
                app_name=args.app,
                category=args.category,
                key_or_index=key_val,
                index=idx_val,
                reload_bab=args.reload,
            )
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"✅ 成功删除规则: [{res['app']}] 类别: {res['category']} ({target_label})")
                print(f"安全备份已保存至: {res['backup_file']}")
                if res.get("reloaded"):
                    print("✅ BetterAndBetter 进程已自动重新加载。")
        except Exception as e:
            print(f"❌ 规则删除失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.set_type == "script":
        if not args.name:
            print("错误: 请通过 --name 指定 AppleScript 名称", file=sys.stderr)
            sys.exit(1)
        if not args.code:
            print("错误: 请通过 --code 指定 AppleScript 代码内容", file=sys.stderr)
            sys.exit(1)

        try:
            res = add_or_update_applescript(
                plist_path=target_path,
                name=args.name,
                code=args.code,
                note=args.note or "",
                reload_bab=args.reload,
            )
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                op_zh = "新增" if res["operation"] == "added" else "更新"
                print(f"✅ 成功{op_zh} AppleScript: [{res['name']}] (ID: {res['id']})")
                print(f"安全备份已保存至: {res['backup_file']}")
                if res.get("reloaded"):
                    print("✅ BetterAndBetter 进程已自动重新加载。")
        except Exception as e:
            print(f"❌ 脚本设置失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.set_type == "remove-script":
        target_name = args.name or args.id
        if not target_name:
            print("错误: 请通过 --name 或 --id 指定要删除的 AppleScript", file=sys.stderr)
            sys.exit(1)
        try:
            res = remove_applescript(
                plist_path=target_path,
                name_or_id=target_name,
                reload_bab=args.reload,
            )
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"✅ 成功删除 AppleScript: [{res['name']}] (ID: {res['id']})")
                print(f"安全备份已保存至: {res['backup_file']}")
                if res.get("reloaded"):
                    print("✅ BetterAndBetter 进程已自动重新加载。")
        except Exception as e:
            print(f"❌ 脚本删除失败: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_clone(args):
    target_path = LIVE_PREFS_PATH if args.target == "live" else REPO_PREFS_PATH
    try:
        res = clone_app_rules(
            plist_path=target_path,
            from_app=args.from_app,
            to_app=args.to_app,
            categories=args.category,
            overwrite=args.overwrite,
            only_enabled=args.only_enabled,
            reload_bab=args.reload,
        )
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 成功从 [{res['from_app']}] 克隆规则至 [{res['to_app']}]！")
            print(f"统计: 新增 {res['added_count']} 条, 更新 {res['updated_count']} 条, 跳过已有 {res['skipped_count']} 条。")
            if res.get("rules"):
                print("\n【克隆/迁移明细】")
                for r in res["rules"]:
                    status_str = r["status"]
                    icon = "➕" if status_str == "added" else ("🔄" if status_str == "updated" else "⏭️")
                    en_str = "启用" if r.get("enable") else "禁用"
                    cat_name = RULE_CATEGORY_TITLES.get(r['category'], r['category'])
                    act = r.get("action")
                    act_display = act if isinstance(act, str) else str(act)
                    print(f"  {icon} [{cat_name}] {r['gesture']:<18} | 状态: {en_str:<2} | {status_str} | 动作: {act_display}")
            print(f"\n安全备份已保存至: {res['backup_file']}")
            if res.get("reloaded"):
                print("✅ BetterAndBetter 进程已自动重新加载生效。")
    except Exception as e:
        print(f"❌ 克隆规则失败: {e}", file=sys.stderr)
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="bab",
        description="BetterAndBetter (BAB 2.7.9) 统一控制、诊断与对账 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
常用示例:
  bab status                           # 查看运行状态、配置对账与统计
  bab inspect                          # 列出所有已配置应用
  bab inspect keyboard --app obsidian  # 查看 Obsidian 的键盘规则
  bab explain "⌘B"                     # 诊断 ⌘B 快捷键在各应用的生效与遮蔽情况
  bab explain "Obsidian"               # 诊断 Obsidian 的专属规则与继承逻辑
  bab explain "ego lite"               # 诊断未配置应用的回退逻辑
  bab diff                             # 对账 Live 本地偏好与 Git 备份仓库差异
  bab sync --to-git                    # 同步 Live 配置到 Git 备份目录
  bab sync --to-live --reload          # 恢复 Git 配置到 Live 并重启生效
  bab set rule --app "com.google.antigravity" --key "⌘K" --action-type Preset --action Center --reload
  bab set toggle --app "md.obsidian" --key "⌘R" --disable --reload
  bab clone --from "Google Chrome" --to "ego lite" --reload  # 模仿 Chrome 配置 Ego Browser 快捷键与手势
  bab reload                           # 干净重启 BetterAndBetter
  bab backup                           # 执行 Git 备份与提交
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 1. status
    p_status = subparsers.add_parser("status", help="检查 BetterAndBetter 运行状态、配置与对账概览")
    p_status.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_status.set_defaults(func=cmd_status)

    # 2. inspect
    p_inspect = subparsers.add_parser("inspect", help="检查配置的应用、快捷键规则或 AppleScript")
    p_inspect.add_argument("category", nargs="?", default=None, choices=["apps", "keyboard", "trackpad", "magicmouse", "normalmouse", "hotcorners", "applescript"], help="筛选类别 (默认列出所有应用)")
    p_inspect.add_argument("--app", help="按应用名称或 Bundle ID 筛选 (如 obsidian, finder)")
    p_inspect.add_argument("--enabled-only", action="store_true", help="仅显示已启用的规则")
    p_inspect.add_argument("--source", choices=["live", "git"], default="live", help="配置数据源 (默认 live)")
    p_inspect.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_inspect.set_defaults(func=cmd_inspect)

    # 3. explain / diagnose
    p_explain = subparsers.add_parser("explain", aliases=["diagnose"], help="诊断优先: 深度分析快捷键冲突、应用遮蔽与状态漂移")
    p_explain.add_argument("query", help="诊断查询词 (快捷键如 '⌘B', 应用如 'Obsidian'/'ego lite', 手势或动作关键字)")
    p_explain.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_explain.set_defaults(func=cmd_explain)

    # 4. diff
    p_diff = subparsers.add_parser("diff", help="对账器: 深度对比 Live 本地生效配置与 Git 备份仓库差异")
    p_diff.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_diff.set_defaults(func=cmd_diff)

    # 5. sync
    p_sync = subparsers.add_parser("sync", help="双向同步 Live 本地偏好与 Git 仓库")
    p_sync.add_argument("--to-git", action="store_true", default=True, help="同步 Live 本地偏好 -> Git 仓库 (默认)")
    p_sync.add_argument("--to-live", action="store_true", help="从 Git 仓库恢复 -> Live 本地偏好")
    p_sync.add_argument("--dry-run", action="store_true", help="试运行预览，不实际写入文件")
    p_sync.add_argument("--reload", action="store_true", help="同步后自动热重启 BetterAndBetter")
    p_sync.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_sync.set_defaults(func=cmd_sync)

    # 6. set
    p_set = subparsers.add_parser("set", help="安全修改规则、状态切换与 AppleScript 配置")
    p_set_subs = p_set.add_subparsers(dest="set_type", required=True, help="修改类型")

    # set rule
    p_set_rule = p_set_subs.add_parser("rule", help="添加或更新规则")
    p_set_rule.add_argument("--app", default="All Applications", help="应用名称或 Bundle ID (默认 All Applications)")
    p_set_rule.add_argument("--category", default="keyboard", choices=["keyboard"], help="规则分类 (默认 keyboard)")
    p_set_rule.add_argument("--key", required=True, help="快捷键 (例如 '⌘B', 'cmd+b', '⇧⌘N')")
    p_set_rule.add_argument("--action-type", default="Preset", choices=["Preset", "Shortcut Keys", "AppleScript"], help="动作类型")
    p_set_rule.add_argument("--action", required=True, help="具体动作 (例如 'Half_of_Top', '⌘C', 或脚本名)")
    p_set_rule.add_argument("--enable", action="store_true", default=True, help="启用该规则 (默认)")
    p_set_rule.add_argument("--disable", action="store_true", help="禁用该规则")
    p_set_rule.add_argument("--note", default="", help="规则备注说明")
    p_set_rule.add_argument("--target", choices=["live", "git"], default="live", help="写入目标 (默认 live)")
    p_set_rule.add_argument("--reload", action="store_true", help="修改后自动重启 BetterAndBetter")
    p_set_rule.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # set toggle
    p_set_toggle = p_set_subs.add_parser("toggle", help="启用/禁用指定规则")
    p_set_toggle.add_argument("--app", default="All Applications", help="应用名称或 Bundle ID")
    p_set_toggle.add_argument("--category", default="keyboard", help="规则分类 (默认 keyboard)")
    p_set_toggle.add_argument("--key", help="快捷键匹配 (例如 '⌘B')")
    p_set_toggle.add_argument("--index", type=int, help="规则索引序号 (从0开始)")
    p_set_toggle.add_argument("--enable", action="store_true", help="显式设为启用")
    p_set_toggle.add_argument("--disable", action="store_true", help="显式设为禁用")
    p_set_toggle.add_argument("--target", choices=["live", "git"], default="live", help="写入目标 (默认 live)")
    p_set_toggle.add_argument("--reload", action="store_true", help="修改后自动重启 BetterAndBetter")
    p_set_toggle.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # set script
    p_set_script = p_set_subs.add_parser("script", help="添加或更新 AppleScript")
    p_set_script.add_argument("--name", required=True, help="AppleScript 脚本名称")
    p_set_script.add_argument("--code", required=True, help="AppleScript 脚本代码")
    p_set_script.add_argument("--note", default="", help="脚本备注说明")
    p_set_script.add_argument("--target", choices=["live", "git"], default="live", help="写入目标 (默认 live)")
    p_set_script.add_argument("--reload", action="store_true", help="修改后自动重启 BetterAndBetter")
    p_set_script.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # set remove-rule
    p_set_rm_rule = p_set_subs.add_parser("remove-rule", help="删除指定规则")
    p_set_rm_rule.add_argument("--app", default="All Applications", help="应用名称或 Bundle ID")
    p_set_rm_rule.add_argument("--category", default="keyboard", help="规则分类 (默认 keyboard)")
    p_set_rm_rule.add_argument("--key", help="快捷键匹配 (例如 '⌘B')")
    p_set_rm_rule.add_argument("--index", type=int, help="规则索引序号 (从0开始)")
    p_set_rm_rule.add_argument("--target", choices=["live", "git"], default="live", help="写入目标 (默认 live)")
    p_set_rm_rule.add_argument("--reload", action="store_true", help="修改后自动重启 BetterAndBetter")
    p_set_rm_rule.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # set remove-script
    p_set_rm_script = p_set_subs.add_parser("remove-script", help="删除指定 AppleScript")
    p_set_rm_script.add_argument("--name", help="AppleScript 名称")
    p_set_rm_script.add_argument("--id", help="AppleScript ID")
    p_set_rm_script.add_argument("--target", choices=["live", "git"], default="live", help="写入目标 (默认 live)")
    p_set_rm_script.add_argument("--reload", action="store_true", help="修改后自动重启 BetterAndBetter")
    p_set_rm_script.add_argument("--json", action="store_true", help="输出 JSON 格式")

    p_set.set_defaults(func=cmd_set)

    # 7. clone / mimic / copy
    p_clone = subparsers.add_parser("clone", aliases=["mimic", "copy"], help="将某一应用的规则克隆/迁移至另一应用 (例如 Chrome -> Ego Browser)")
    p_clone.add_argument("--from", dest="from_app", required=True, help="源应用名称或 Bundle ID (例如 'Google Chrome')")
    p_clone.add_argument("--to", dest="to_app", required=True, help="目标应用名称或 Bundle ID (例如 'ego lite' 或 'com.citrolabs.ego.lite')")
    p_clone.add_argument("--category", "-c", nargs="*", default=None, help="指定要克隆的规则分类 (默认全部，如 keyboard trackpad normalmouse)")
    p_clone.add_argument("--overwrite", action="store_true", help="如果目标应用已存在相同快捷键/手势，则覆盖；默认保留已有配置")
    p_clone.add_argument("--only-enabled", action="store_true", help="仅克隆已启用的规则 (跳过禁用的规则)")
    p_clone.add_argument("--target", choices=["live", "git"], default="live", help="写入目标 (默认 live)")
    p_clone.add_argument("--reload", action="store_true", help="修改后自动干净重启 BetterAndBetter")
    p_clone.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_clone.set_defaults(func=cmd_clone)

    # 8. backup
    p_backup = subparsers.add_parser("backup", help="执行 Git 备份或管理自动备份守护进程")
    p_backup.add_argument("--daemon-status", action="store_true", help="查看自动备份守护进程与 LaunchAgent 状态")
    p_backup.add_argument("--install-daemon", action="store_true", help="安装并激活自动备份 LaunchAgent 守护进程")
    p_backup.add_argument("--uninstall-daemon", action="store_true", help="卸载并清理自动备份 LaunchAgent 守护进程")
    p_backup.add_argument("--force", action="store_true", help="强制重新安装/覆盖现有守护进程")
    p_backup.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_backup.set_defaults(func=cmd_backup)

    # 9. reload
    p_reload = subparsers.add_parser("reload", help="干净热重启 BetterAndBetter 应用程序")
    p_reload.set_defaults(func=cmd_reload)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
