#!/usr/bin/env python3
"""Run only after approving creation of user application-menu/desktop files."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from anki_ai_vocab.desktop import install_launchers
from anki_ai_vocab.errors import VocabError


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 AI 英语收词的用户级启动图标")
    parser.add_argument("--applications-dir", type=Path)
    parser.add_argument("--desktop-dir", type=Path)
    parser.add_argument("--menu-only", action="store_true", help="仅安装应用菜单入口")
    args = parser.parse_args()
    applications_dir = args.applications_dir or (
        Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        / "applications"
    )
    desktop_dir = args.desktop_dir
    if not args.menu_only and desktop_dir is None:
        if shutil.which("xdg-user-dir"):
            result = subprocess.run(
                ["xdg-user-dir", "DESKTOP"],
                capture_output=True,
                text=True,
                check=True,
            )
            desktop_dir = Path(result.stdout.strip()) if result.stdout.strip() else None
        else:
            desktop_dir = Path.home() / "Desktop"
        if desktop_dir == Path.home():
            desktop_dir = None
    if args.menu_only:
        desktop_dir = None
    try:
        paths = install_launchers(
            Path(__file__).resolve().parents[1],
            applications_dir,
            desktop_dir,
        )
    except (VocabError, OSError) as exc:
        print(f"安装失败：{exc}")
        return 1
    for path in paths:
        print(f"启动图标已就绪：{path}")
    print("可从应用菜单打开。桌面图标如提示不受信任，请右键选择“允许启动”。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
