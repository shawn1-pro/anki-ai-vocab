"""X11/Wayland clipboard adapters and sentence word selection."""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from .errors import ClipboardError, ValidationError
from .vocabulary import normalize, validate_word

# Retain technical tokens such as C++, C#, snake_case and hyphenated words.
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:['’.-][A-Za-z0-9_]+)*(?:\+\+|#)?")


@dataclass(frozen=True)
class ClipboardText:
    text: str
    words: tuple[str, ...]
    single: bool


def clipboard_commands() -> list[list[str]]:
    x11 = [
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ]
    wayland = [["wl-paste", "--no-newline", "--type", "text"]]
    if os.getenv("XDG_SESSION_TYPE") == "wayland" or os.getenv("WAYLAND_DISPLAY"):
        return wayland + x11
    return x11 + wayland


def read_clipboard() -> str:
    attempted = False
    for command in clipboard_commands():
        if not shutil.which(command[0]):
            continue
        attempted = True
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=3,
                check=True,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError):
            continue
        if result.stdout.strip():
            return result.stdout
    if not attempted:
        raise ClipboardError(
            "未找到剪贴板工具。X11 请安装 xclip/xsel，Wayland 请安装 wl-clipboard。"
        )
    raise ClipboardError("无法读取文本剪贴板；请重新复制，并在当前图形桌面会话运行。")


def process_text(text: str) -> ClipboardText:
    text = text.strip()
    if not text:
        raise ClipboardError("剪贴板为空。")
    if len(text) > 8000:
        raise ClipboardError("剪贴板超过 8000 字符，请只复制需要学习的原句。")
    words = tuple(dict.fromkeys(TOKEN.findall(text)))
    if not words:
        raise ClipboardError("剪贴板中没有英文单词。")
    return ClipboardText(text, words, bool(TOKEN.fullmatch(text)))


def select_word(
    data: ClipboardText,
    selected: str | None = None,
    ask: Callable[[str], str] = input,
) -> tuple[str, str]:
    if data.single:
        if selected and normalize(selected) != normalize(data.text):
            raise ValidationError("--word 必须是剪贴板中的单词。")
        return validate_word(data.text), ""
    if selected:
        selected = validate_word(selected)
        if normalize(selected) not in {normalize(w) for w in data.words}:
            raise ValidationError("--word 必须从原句中的单词选择。")
        return selected, data.text
    print("原句：", data.text)
    for number, word in enumerate(data.words, 1):
        print(f"  {number}. {word}")
    while True:
        answer = ask("输入单词编号或原句中的单词（回车取消）：").strip()
        if not answer:
            raise ClipboardError("已取消选择。")
        if answer.isdigit() and 1 <= int(answer) <= len(data.words):
            return data.words[int(answer) - 1], data.text
        try:
            return select_word(data, answer, ask)
        except ValidationError as exc:
            print(str(exc))
