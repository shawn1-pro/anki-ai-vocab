import os
import shutil
import subprocess
from pathlib import Path

import pytest

from anki_ai_vocab.desktop import desktop_entry, install_launchers
from anki_ai_vocab.errors import VocabError

PROJECT = Path(__file__).resolve().parents[1]


def test_launcher_is_terminal_free_and_points_to_project(tmp_path):
    content = desktop_entry(tmp_path)
    assert "Terminal=false" in content
    assert f'Exec=/bin/bash "{tmp_path}/scripts/launch_gui.sh"' in content
    assert "DEEPSEEK_API_KEY" not in content


def test_launcher_installs_only_to_requested_directories(tmp_path):
    menu, desktop = tmp_path / "applications", tmp_path / "desktop"
    paths = install_launchers(PROJECT, menu, desktop)
    assert paths == [menu / "anki-ai-vocab.desktop", desktop / "anki-ai-vocab.desktop"]
    assert all(p.is_file() and os.access(p, os.X_OK) for p in paths)
    assert install_launchers(PROJECT, menu, desktop) == paths


def test_existing_launcher_is_never_overwritten(tmp_path):
    menu, desktop = tmp_path / "applications", tmp_path / "desktop"
    desktop.mkdir()
    existing = desktop / "anki-ai-vocab.desktop"
    existing.write_text("user content")
    with pytest.raises(VocabError, match="未覆盖"):
        install_launchers(PROJECT, menu, desktop)
    assert existing.read_text() == "user content"
    assert not menu.exists()


@pytest.mark.skipif(
    not shutil.which("desktop-file-validate"), reason="validator not installed"
)
def test_desktop_entry_special_paths_validate(tmp_path):
    content = desktop_entry(tmp_path / 'project space $money `tick` "quote" 100%')
    desktop_file = tmp_path / "anki-ai-vocab.desktop"
    desktop_file.write_text(content)
    subprocess.run(["desktop-file-validate", str(desktop_file)], check=True)


def test_install_command_supports_explicit_test_paths(tmp_path):
    subprocess.run(
        [
            str(PROJECT / ".venv/bin/python"),
            str(PROJECT / "scripts/install_desktop.py"),
            "--applications-dir",
            str(tmp_path / "menu"),
            "--desktop-dir",
            str(tmp_path / "desktop"),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert (tmp_path / "menu/anki-ai-vocab.desktop").is_file()
