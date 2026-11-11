#!/usr/bin/env bash
# Launch from GNOME without depending on shell startup files or an open terminal.
set -u

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${project_dir}/.venv/bin/python"
cd -- "$project_dir" || exit 1

if [[ ! -x "$python_bin" ]]; then
    error_text='缺少项目虚拟环境，请按 README 安装 .venv。'
    exit_code=1
elif error_text="$("$python_bin" -m anki_ai_vocab gui "$@" 2>&1)"; then
    exit 0
else
    exit_code=$?
fi

if command -v zenity >/dev/null 2>&1; then
    zenity --error --title='AI 英语收词启动失败' --no-markup --text="$error_text" || true
else
    printf '%s\n' "$error_text" >&2
fi
exit "$exit_code"
