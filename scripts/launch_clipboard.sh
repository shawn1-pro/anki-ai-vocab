#!/usr/bin/env bash
# Stable cwd, interpreter and .env location when launched from GNOME.
set -u

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${project_dir}/.venv/bin/python"

if [[ "${1:-}" == "--inside-terminal" ]]; then
    shift
    cd -- "$project_dir" || exit 1
    if [[ ! -x "$python_bin" ]]; then
        printf '%s\n' '缺少 .venv。请先按 README 安装项目。'
        exit_code=1
    else
        "$python_bin" -m anki_ai_vocab clipboard "$@"
        exit_code=$?
    fi
    printf '\n%s\n' '按回车关闭窗口。'
    read -r _ || true
    exit "$exit_code"
fi

if command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal --wait --title='AI 英语收词' -- \
        /bin/bash "${project_dir}/scripts/launch_clipboard.sh" --inside-terminal "$@"
elif command -v x-terminal-emulator >/dev/null 2>&1; then
    exec x-terminal-emulator -e /bin/bash \
        "${project_dir}/scripts/launch_clipboard.sh" --inside-terminal "$@"
else
    printf '%s\n' '未找到终端模拟器，请安装 gnome-terminal 或在终端运行 anki-word clipboard。' >&2
    exit 1
fi
