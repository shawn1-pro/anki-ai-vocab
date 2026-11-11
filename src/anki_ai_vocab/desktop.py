"""Generate and install user-level desktop launchers without system changes."""

from pathlib import Path

from .errors import VocabError


def desktop_entry(project_dir: Path) -> str:
    launcher = str(project_dir.resolve() / "scripts" / "launch_gui.sh")
    # Desktop Entry values and Exec argument quoting have separate escape layers.
    argument = launcher.replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        argument = argument.replace(char, "\\" + char)
    argument = argument.replace("\\", "\\\\")
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=AI 英语收词\n"
        "Name[en]=AI Vocabulary\n"
        "Comment=输入单词，生成例句，确认保存到 Anki\n"
        f'Exec=/bin/bash "{argument}"\n'
        "Icon=accessories-dictionary\n"
        "Terminal=false\n"
        "Categories=Education;Languages;\n"
        "Keywords=Anki;English;Vocabulary;英语;单词;\n"
        "StartupNotify=false\n"
    )


def install_launchers(
    project_dir: Path,
    applications_dir: Path,
    desktop_dir: Path | None = None,
) -> list[Path]:
    content = desktop_entry(project_dir)
    directories = [applications_dir] + ([desktop_dir] if desktop_dir else [])
    targets = [directory / "anki-ai-vocab.desktop" for directory in directories]
    for target in targets:
        if target.exists() and (target.is_symlink() or target.read_text() != content):
            raise VocabError(f"启动图标已存在且内容不同，未覆盖：{target}")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("x", encoding="utf-8") as stream:
                stream.write(content)
            target.chmod(0o755)
    return targets
