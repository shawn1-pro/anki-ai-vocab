import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "launch_clipboard.sh"


@pytest.mark.parametrize("terminal", ["gnome-terminal", "x-terminal-emulator"])
def test_launcher_keeps_absolute_paths_and_quoted_arguments(tmp_path, terminal):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    (binary_dir / "dirname").symlink_to(shutil.which("dirname"))
    terminal_stub = binary_dir / terminal
    terminal_stub.write_text(
        f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n"
    )
    terminal_stub.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(LAUNCHER), "--topic", "Control Theory"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(binary_dir)},
        capture_output=True,
        text=True,
        check=True,
    )
    arguments = json.loads(result.stdout)
    assert str(LAUNCHER) in arguments
    assert arguments[-3:] == ["--inside-terminal", "--topic", "Control Theory"]


def test_launcher_reports_missing_terminal(tmp_path):
    (tmp_path / "dirname").symlink_to(shutil.which("dirname"))
    result = subprocess.run(
        ["/bin/bash", str(LAUNCHER)],
        env={**os.environ, "PATH": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "未找到终端模拟器" in result.stderr


def test_gui_launcher_uses_project_environment_without_terminal(tmp_path):
    project = tmp_path / "project with spaces"
    (project / "scripts").mkdir(parents=True)
    (project / ".venv/bin").mkdir(parents=True)
    launcher = project / "scripts/launch_gui.sh"
    shutil.copyfile(LAUNCHER.parent / "launch_gui.sh", launcher)
    capture = tmp_path / "launch_args.json"
    python_stub = project / ".venv/bin/python"
    python_stub.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "Path(os.environ['ANKI_GUI_CAPTURE']).write_text("
        "json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}))\n"
    )
    python_stub.chmod(0o755)
    subprocess.run(
        ["/bin/bash", str(launcher)],
        cwd=tmp_path,
        env={**os.environ, "ANKI_GUI_CAPTURE": str(capture)},
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(capture.read_text())
    assert result["args"] == ["-m", "anki_ai_vocab", "gui"]
    assert result["cwd"] == str(project)
