#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""thesis-topic-pipeline 的 CNKI MCP 引导脚本。

检测 → 安装 → 打开浏览器登录 → 打印配置块。

用法：
    python scripts/bootstrap.py --check     # 只检测，不安装（安全）
    python scripts/bootstrap.py             # 缺什么装什么，最后引导登录

退出码：0 就绪；1 失败；2 需要人工完成登录。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home() / ".cnki-mcp"
VENV = HOME / "venv"
PROFILES = HOME / "profiles"
MIRROR = "https://npmmirror.com/mirrors/playwright"
MIN_PY = (3, 11)


def is_windows() -> bool:
    return platform.system() == "Windows"


def bin_dir() -> Path:
    return VENV / ("Scripts" if is_windows() else "bin")


def exe(name: str) -> Path:
    return bin_dir() / (name + ".exe" if is_windows() else name)


def run(cmd: list[str], env: dict | None = None, quiet: bool = False) -> int:
    merged = {**os.environ, **(env or {})}
    if not quiet:
        print("  $", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call([str(c) for c in cmd], env=merged)


def find_existing_cli() -> str | None:
    """已经装过就复用，避免重复装一份。"""
    found = shutil.which("cnki-mcp")
    if found:
        return found
    return None


def probe() -> dict:
    """只读检测，不产生任何副作用。"""
    existing = find_existing_cli()
    cli = existing or str(exe("cnki-mcp"))
    state = {
        "python": platform.python_version(),
        "python_ok": sys.version_info[:2] >= MIN_PY,
        "platform": platform.system(),
        "venv": str(VENV),
        "venv_exists": VENV.exists(),
        "cli": cli,
        "cli_source": "PATH" if existing else "bootstrap-venv",
        "cli_exists": Path(cli).exists(),
        "profile_dir": str(PROFILES),
        "profile_exists": PROFILES.exists() and any(PROFILES.iterdir()) if PROFILES.exists() else False,
        "ready": False,
    }
    state["ready"] = state["python_ok"] and state["cli_exists"] and state["profile_exists"]
    return state


def ensure_venv() -> None:
    if not VENV.exists():
        print(f"[1/4] 创建虚拟环境 {VENV}", flush=True)
        HOME.mkdir(parents=True, exist_ok=True)
        if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
            raise SystemExit("创建 venv 失败")
    else:
        print(f"[1/4] 虚拟环境已存在 {VENV}", flush=True)


def ensure_package() -> None:
    py = exe("python")
    print("[2/4] 安装 cnki-mcp（约几十 MB）", flush=True)
    run([py, "-m", "pip", "install", "--upgrade", "pip", "-q"], quiet=True)
    if run([py, "-m", "pip", "install", "--upgrade", "cnki-mcp", "-q"]) != 0:
        raise SystemExit("安装 cnki-mcp 失败，检查网络后重试")


def ensure_chromium() -> None:
    py = exe("python")
    print("[3/4] 安装 Playwright Chromium（约 700MB，可复用缓存）", flush=True)
    if run([py, "-m", "playwright", "install", "chromium"]) == 0:
        return
    print("  直连失败，改用镜像重试……", flush=True)
    if run([py, "-m", "playwright", "install", "chromium"],
           env={"PLAYWRIGHT_DOWNLOAD_HOST": MIRROR}) != 0:
        raise SystemExit("Chromium 安装失败；可手动设置 PLAYWRIGHT_DOWNLOAD_HOST 后重试")


def do_login(cli: str, profile: str) -> int:
    print("[4/4] 打开浏览器，请在窗口里完成学校认证", flush=True)
    print("      校内走机构认证；校外走 CARSI；不要点「IP 登录」", flush=True)
    print("      窗口只等约 2 分钟，超时就重跑本脚本", flush=True)
    code = run([cli, "init", "--profile", profile])
    return code


def print_config(cli: str, profile: str) -> None:
    cfg = {
        "mcpServers": {
            "cnki": {
                "command": cli,
                "args": ["serve", "--transport", "stdio"],
                "timeout": 180000,
            }
        }
    }
    print("\n=== 把下面这段写进你的 MCP 客户端配置 ===", flush=True)
    print(json.dumps(cfg, ensure_ascii=False, indent=2), flush=True)
    print(f"\nprofile: {profile}", flush=True)
    print("提醒：stdio 模式每个新会话先调用一次 login。", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检测，不安装")
    ap.add_argument("--profile", default="default")
    args = ap.parse_args()

    state = probe()

    if args.check:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0 if state["ready"] else 1

    if state["ready"]:
        print("已就绪，无需安装。", flush=True)
        print_config(state["cli"], args.profile)
        return 0

    if not state["python_ok"]:
        raise SystemExit(
            f"需要 Python {MIN_PY[0]}.{MIN_PY[1]}+，当前 {state['python']}"
        )

    ensure_venv()
    ensure_package()
    ensure_chromium()
    code = do_login(state["cli"], args.profile)

    after = probe()
    if after["ready"]:
        print("\n✔ 安装完成，浏览器资料已保存。", flush=True)
        print_config(after["cli"], args.profile)
        return 0

    print("\n✘ 登录未完成（窗口超时或被关闭）。重跑本脚本即可，无需重装。", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
