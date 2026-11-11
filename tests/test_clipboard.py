import subprocess
from types import SimpleNamespace

import pytest

from anki_ai_vocab import clipboard
from anki_ai_vocab.errors import ClipboardError, ValidationError


@pytest.mark.parametrize(
    "word", ["degeneracy", "C++", "C#", "snake_case", "state-estimation"]
)
def test_single_word(word):
    data = clipboard.process_text(f" \n{word}\n")
    assert data.single
    assert clipboard.select_word(data) == (word, "")


def test_sentence_selection_preserves_full_context():
    sentence = "Geometric degeneracy\nmay cause localization drift."
    data = clipboard.process_text(sentence)
    word, context = clipboard.select_word(data, ask=lambda _: "2")
    assert word == "degeneracy"
    assert context == sentence
    assert clipboard.select_word(data, selected="Drift") == ("Drift", sentence)


def test_invalid_selection_reprompts():
    answers = iter(["999", "wrong", "degeneracy"])
    data = clipboard.process_text("Geometric degeneracy causes drift.")
    assert clipboard.select_word(data, ask=lambda _: next(answers))[0] == "degeneracy"


def test_explicit_word_must_occur_in_sentence():
    with pytest.raises(ValidationError):
        clipboard.select_word(clipboard.process_text("Geometric degeneracy."), "robot")


@pytest.mark.parametrize("text", ["", "中文文字", "a" * 8001])
def test_invalid_clipboard_text(text):
    with pytest.raises(ClipboardError):
        clipboard.process_text(text)


def test_wayland_order(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert clipboard.clipboard_commands()[0][0] == "wl-paste"


def test_x11_order(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert clipboard.clipboard_commands()[0][0] == "xclip"


def test_clipboard_fallback_on_failure(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/mock/{name}")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "xclip":
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="degeneracy")

    monkeypatch.setattr(clipboard.subprocess, "run", run)
    assert clipboard.read_clipboard() == "degeneracy"
    assert [call[0][0] for call in calls] == ["xclip", "xsel"]
    assert calls[0][1]["timeout"] == 3
    assert "shell" not in calls[0][1]


def test_missing_tools(monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", lambda _: None)
    with pytest.raises(ClipboardError, match="未找到"):
        clipboard.read_clipboard()
